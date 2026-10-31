"""OcrClient against an in-process httpx MockTransport. These are NOT real OCR tests."""

import json

import httpx
import pytest

from billing_agent.config import OcrSettings
from billing_agent.services.ocr_client import OcrClient, OcrError
from fakes import ocr_payload

URL = "https://bucket.oss-cn-shanghai.aliyuncs.com/ocr-tmp/a.pdf?Signature=x"


def client_with(handler) -> OcrClient:
    return OcrClient(OcrSettings(), http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_request_body_matches_assignment_contract():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ocr_payload())

    resp = client_with(handler).process(URL)
    assert seen["url"] == "https://gateway.pltplt.com/ai/process"
    assert seen["body"] == {"file": URL, "task": "orderChange", "callBack": "", "taskType": ""}
    assert resp.payload["data"]["list"][0]["invoiceNumber"] == "SYN-INV-9"


@pytest.mark.parametrize("bad", ["C:\\bill.pdf", "/tmp/a.pdf", "http://x.com/a.pdf", "https://127.0.0.1/a"])
def test_local_or_unsafe_url_is_never_sent(bad):
    called = []
    client = client_with(lambda r: called.append(r) or httpx.Response(200, json=ocr_payload()))
    with pytest.raises(OcrError) as exc:
        client.process(bad)
    assert exc.value.code == "INVALID_URL"
    assert called == []


def test_gateway_504_html():
    html = "<html><head><title>504 Gateway Time-out</title></head><body>nginx</body></html>"
    client = client_with(lambda r: httpx.Response(504, text=html, headers={"content-type": "text/html"}))
    with pytest.raises(OcrError) as exc:
        client.process(URL)
    assert exc.value.code == "HTTP_ERROR" and exc.value.http_status == 504
    assert "<html>" not in exc.value.message


def test_non_json_200():
    with pytest.raises(OcrError) as exc:
        client_with(lambda r: httpx.Response(200, text="ok")).process(URL)
    assert exc.value.code == "INVALID_RESPONSE"


def test_success_false():
    with pytest.raises(OcrError) as exc:
        client_with(lambda r: httpx.Response(200, json=ocr_payload(success=False))).process(URL)
    assert exc.value.code == "OCR_REPORTED_FAILURE"


def test_missing_data_list():
    with pytest.raises(OcrError) as exc:
        client_with(lambda r: httpx.Response(200, json={"success": True, "data": {}})).process(URL)
    assert exc.value.code == "UNEXPECTED_SCHEMA"


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(OcrError) as exc:
        client_with(handler).process(URL)
    assert exc.value.code == "TIMEOUT"


def test_network_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(OcrError) as exc:
        client_with(handler).process(URL)
    assert exc.value.code == "NETWORK_ERROR"


def test_signed_url_not_logged(caplog):
    caplog.set_level("INFO")
    client_with(lambda r: httpx.Response(200, json=ocr_payload())).process(URL)
    assert "Signature" not in caplog.text
