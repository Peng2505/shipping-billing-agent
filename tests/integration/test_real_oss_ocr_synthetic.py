"""Real OSS + OCR path using SYNTHETIC files only (no recruiter samples).

Run: pytest --run-real -m "real_oss or real_ocr" tests/integration/test_real_oss_ocr_synthetic.py -v

Never prints AccessKeys or full signed URLs.
"""

from __future__ import annotations

import re

import httpx
import pytest

import synthetic_builders as sb
from billing_agent.config import load_settings
from billing_agent.security import redact_url, short_hash
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.ocr_service import OcrService
from billing_agent.services.oss_storage import AliyunOSSStorage, StorageError
from billing_agent.schemas import OcrStatus

_SENSITIVE = re.compile(r"(accesskey|secret|signature|security-token|session)=[^\s&]+", re.I)


def _safe(text: str) -> str:
    text = _SENSITIVE.sub(lambda m: m.group(0).split("=", 1)[0] + "=***", text)
    return text[:300]


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _require_oss(settings):
    if not settings.oss.configured:
        pytest.skip(f"BLOCKED: OSS not configured ({', '.join(settings.oss.missing_fields())})")


def _classify_oss_error(exc: BaseException) -> str:
    msg = _safe(str(exc))
    low = msg.lower()
    if "publicendpointforbidden" in low or "public endpoint" in low:
        return "PUBLIC_ENDPOINT_FORBIDDEN"
    if "accessdenied" in low or "access denied" in low or "403" in low:
        return "RAM_OR_ACL_DENIED"
    if "invalidaccesskey" in low or "signaturedoesnotmatch" in low or "signature" in low:
        return "SIGNATURE_OR_KEY_ERROR"
    if "nosuchbucket" in low:
        return "BUCKET_NOT_FOUND"
    if "timeout" in low:
        return "TIMEOUT"
    return f"OTHER:{type(exc).__name__}"


@pytest.mark.real_oss
def test_synthetic_oss_upload_sign_download_delete(settings):
    _require_oss(settings)
    storage = AliyunOSSStorage(settings.oss)
    payload = sb.pdf_bytes(
        "SYNTHETIC TEST DATA\nInvoice SYN-INV-OSS-1\nHandling Fee USD 40.00\nTotal USD 40.00"
    )
    try:
        temp = storage.put_temporary(payload, ".pdf", "application/pdf")
    except StorageError as exc:
        pytest.fail(f"OSS upload FAILED [{_classify_oss_error(exc)}]: {_safe(exc.message)}")

    key_hash = short_hash(temp.key)
    redacted = redact_url(temp.url)
    assert temp.url.lower().startswith("https://"), "signed URL must be https"
    assert "Signature" not in redacted and "signature" not in redacted.lower()

    try:
        unsigned = temp.url.split("?", 1)[0]
        public_status = httpx.get(unsigned, timeout=30).status_code
        assert public_status == 403, f"object must stay private; got HTTP {public_status}"

        signed = httpx.get(temp.url, timeout=30)
        assert signed.status_code == 200, (
            f"signed GET failed HTTP {signed.status_code} [{_classify_oss_error(Exception(signed.text))}] "
            f"url={redacted} key#{key_hash}"
        )
        assert signed.content == payload
    finally:
        storage.delete(temp.key)

    gone = httpx.get(temp.url, timeout=30).status_code
    assert gone in {403, 404}, f"expected object gone after delete, got {gone}"


@pytest.mark.real_oss
@pytest.mark.real_ocr
def test_synthetic_oss_to_ocr_end_to_end(settings):
    _require_oss(settings)
    service = OcrService.from_settings(settings)
    assert service.configured

    payload = sb.pdf_bytes(
        "SYNTHETIC TEST DATA\nDebit Note SYN-DN-OCR-1\n"
        "Handling Charge USD 40.00\nDocumentation Fee USD 15.00\nTotal USD 55.00"
    )
    outcome = service.recognize(payload, ".pdf")

    if outcome.status == OcrStatus.FAILED:
        code = outcome.error_code or "UNKNOWN"
        detail = _safe(outcome.error_message or "")
        # Distinguish OCR gateway vs storage failures
        if code in {"UPLOAD_FAILED", "SIGN_FAILED", "INSECURE_URL", "DELETE_FAILED", "SIGNED_URL_EXPIRED"}:
            kind = _classify_oss_error(Exception(detail))
            pytest.fail(f"OSS stage FAILED [{kind}/{code}]: {detail}")
        if outcome.http_status in {502, 504} or "504" in detail or "timeout" in detail.lower():
            pytest.fail(f"OCR gateway FAILED [GATEWAY_TIMEOUT/{code}]: http={outcome.http_status} {detail}")
        pytest.fail(f"OCR FAILED [{code}]: http={outcome.http_status} {detail}")

    assert outcome.status == OcrStatus.SUCCESS, outcome
    assert outcome.raw_response and outcome.raw_response.get("success") is True
    assert isinstance(outcome.raw_response.get("data", {}).get("list"), list)
    assert outcome.object_key_hash  # temp object was tracked (and deleted in finally)
    # chargeList may be empty for synthetic text PDFs — that is still a valid OCR response
    item = (outcome.raw_response["data"]["list"] or [{}])[0]
    assert "chargeList" in item
