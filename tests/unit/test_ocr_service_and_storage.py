"""OcrService orchestration and AliyunOSSStorage with fakes. NOT real OCR/OSS tests."""

import re

import httpx
import pytest

import synthetic_builders as sb
from billing_agent.config import OcrSettings, OssSettings
from billing_agent.parsers import ParseContext, parse_bytes
from billing_agent.schemas import OcrStatus, ParseStatus, SourceOrigin
from billing_agent.services.ocr_client import OcrClient
from billing_agent.services.ocr_service import OcrService, assess_payload
from billing_agent.services.oss_storage import AliyunOSSStorage, StorageError, build_object_key
from fakes import FakeOssBucket, FakeUrlProvider, ocr_payload


def service(handler, provider):
    client = OcrClient(OcrSettings(), http=httpx.Client(transport=httpx.MockTransport(handler)))
    return OcrService(client, provider)


def ok(request):
    return httpx.Response(200, json=ocr_payload())


def test_not_configured_never_calls_ocr():
    calls = []
    svc = service(lambda r: calls.append(r) or ok(r), None)
    outcome = svc.recognize(b"data", ".pdf")
    assert outcome.status == OcrStatus.NOT_CONFIGURED
    assert calls == []


def test_success_uploads_calls_and_deletes():
    provider = FakeUrlProvider()
    outcome = service(ok, provider).recognize(b"%PDF-data", ".pdf")
    assert outcome.status == OcrStatus.SUCCESS
    assert provider.uploaded[0][2] == "application/pdf"
    assert provider.deleted == [provider.uploaded[0][0]]
    assert outcome.raw_response["data"]["list"][0]["invoiceNumber"] == "SYN-INV-9"
    assert outcome.object_key_hash and "ocr-tmp" not in outcome.object_key_hash


def test_ocr_failure_still_deletes_object():
    provider = FakeUrlProvider()
    outcome = service(lambda r: httpx.Response(504, text="<html>504</html>"), provider).recognize(b"x", ".png")
    assert outcome.status == OcrStatus.FAILED
    assert outcome.error_code == "HTTP_ERROR" and outcome.http_status == 504
    assert provider.deleted == [provider.uploaded[0][0]]


def test_upload_failure():
    outcome = service(ok, FakeUrlProvider(fail_upload=True)).recognize(b"x", ".png")
    assert outcome.status == OcrStatus.FAILED and outcome.error_code == "UPLOAD_FAILED"


def test_delete_failure_is_reported_as_warning():
    outcome = service(ok, FakeUrlProvider(fail_delete=True)).recognize(b"x", ".pdf")
    assert outcome.status == OcrStatus.SUCCESS
    assert any("lifecycle rule" in w for w in outcome.warnings)


def test_expired_signed_url_is_not_sent():
    calls = []
    provider = FakeUrlProvider(expires_in=10)
    outcome = service(lambda r: calls.append(r) or ok(r), provider).recognize(b"x", ".pdf")
    assert outcome.status == OcrStatus.FAILED and outcome.error_code == "SIGNED_URL_EXPIRED"
    assert calls == [] and provider.deleted


def test_assess_payload_flags_empty_and_suspicious():
    assert "empty data.list" in assess_payload(ocr_payload(items=[]))[0]
    warnings = assess_payload(ocr_payload(items=[{"fileType": "X", "suspicious": "Y", "chargeList": []}]))
    assert any("suspicious" in w for w in warnings)
    assert any("no recognised business fields" in w for w in warnings)


def test_image_parser_with_ocr_adds_ocr_api_block():
    ctx = ParseContext(ocr_service=service(ok, FakeUrlProvider()))
    doc = parse_bytes(sb.png_bytes(), "bill.png", ctx)
    assert doc.status == ParseStatus.PARSED
    blocks = doc.blocks_by_origin(SourceOrigin.OCR_API)
    assert len(blocks) == 1 and "SYN-INV-9" in blocks[0].text
    assert doc.meta["width"] == 40


def test_image_parser_ocr_failure_has_no_text():
    ctx = ParseContext(ocr_service=service(lambda r: httpx.Response(500, text="boom"), FakeUrlProvider()))
    doc = parse_bytes(sb.png_bytes(), "bill.png", ctx)
    assert doc.status == ParseStatus.FAILED
    assert doc.blocks == []
    assert any("OCR failed" in e for e in doc.errors)


def test_pdf_ocr_failure_keeps_text_layer_labelled():
    ctx = ParseContext(ocr_service=service(lambda r: httpx.Response(500, text="boom"), FakeUrlProvider()))
    doc = parse_bytes(sb.pdf_bytes(), "x.pdf", ctx)
    assert doc.status == ParseStatus.PARTIAL
    assert doc.ocr.status == OcrStatus.FAILED
    assert {b.origin for b in doc.blocks} == {SourceOrigin.TEXT_LAYER}


def test_tiff_frames():
    doc = parse_bytes(sb.tiff_bytes(frames=3), "scan.tiff")
    assert doc.meta["frames"] == 3


# ---- AliyunOSSStorage with a fake bucket ----

def oss_settings(**kw):
    base = dict(endpoint="https://oss-cn-test.aliyuncs.com", bucket="b", access_key_id="id",
                access_key_secret="secret", prefix="ocr-tmp/", url_expire_seconds=1800)
    base.update(kw)
    return OssSettings(**base)


def test_object_keys_are_unique_and_safe():
    keys = {build_object_key("ocr-tmp/", ".pdf") for _ in range(50)}
    assert len(keys) == 50
    assert all(re.fullmatch(r"ocr-tmp/\d{8}/[0-9a-f]{32}\.pdf", k) for k in keys)
    assert build_object_key("ocr-tmp", "../../x").endswith(".bin")


def test_oss_put_is_private_no_overwrite_and_signed_30min():
    bucket = FakeOssBucket()
    storage = AliyunOSSStorage(oss_settings(), bucket=bucket)
    temp = storage.put_temporary(b"data", ".pdf", "application/pdf")
    _, headers = bucket.objects[temp.key]
    assert headers["x-oss-object-acl"] == "private"
    assert headers["x-oss-forbid-overwrite"] == "true"
    assert bucket.sign_calls == [("GET", temp.key, 1800, True)]
    assert temp.url.startswith("https://")
    storage.delete(temp.key)
    assert temp.key not in bucket.objects


def test_oss_rejects_http_signed_url_and_cleans_up():
    bucket = FakeOssBucket(sign_scheme="http")
    storage = AliyunOSSStorage(oss_settings(), bucket=bucket)
    with pytest.raises(StorageError) as exc:
        storage.put_temporary(b"data", ".pdf", "application/pdf")
    assert exc.value.code == "INSECURE_URL"
    assert bucket.objects == {}


def test_oss_upload_failure():
    storage = AliyunOSSStorage(oss_settings(), bucket=FakeOssBucket(fail_put=True))
    with pytest.raises(StorageError) as exc:
        storage.put_temporary(b"d", ".png", "image/png")
    assert exc.value.code == "UPLOAD_FAILED"


def test_oss_not_configured():
    assert AliyunOSSStorage.from_settings(OssSettings()) is None
    with pytest.raises(StorageError):
        AliyunOSSStorage(OssSettings())
    assert "OSS_BUCKET" in OssSettings().missing_fields()
