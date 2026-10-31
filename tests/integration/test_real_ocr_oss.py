"""Real external calls. Run with:  pytest --run-real -m "real_ocr or real_oss"

Missing credentials -> pytest.skip with a 'BLOCKED:' reason (never reported as passed).
"""

from __future__ import annotations

import httpx
import pytest

from billing_agent.config import load_settings
from billing_agent.parsers import ParseContext, parse_path
from billing_agent.schemas import OcrStatus, SourceOrigin
from billing_agent.services.ocr_client import OcrClient
from billing_agent.services.ocr_service import OcrService
from billing_agent.services.oss_storage import AliyunOSSStorage
from conftest import SAMPLES_DIR

PUBLIC_NON_SENSITIVE_PDF = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _require_oss(settings):
    if not settings.oss.configured:
        pytest.skip(f"BLOCKED: OSS not configured ({', '.join(settings.oss.missing_fields())})")


@pytest.mark.real_ocr
def test_real_ocr_contract_with_public_file(settings):
    """Contract probe using a public, non-business PDF. Does not need OSS."""
    resp = OcrClient(settings.ocr).process(PUBLIC_NON_SENSITIVE_PDF)
    payload = resp.payload
    assert payload["success"] is True
    item = payload["data"]["list"][0]
    for key in ("fileType", "invoiceNumber", "mblNumber", "chargeList", "ctrList", "page_index"):
        assert key in item


@pytest.mark.real_oss
def test_real_oss_private_object_and_signed_url(settings):
    _require_oss(settings)
    storage = AliyunOSSStorage(settings.oss)
    temp = storage.put_temporary(b"SYNTHETIC TEST DATA", ".txt", "text/plain")
    try:
        unsigned = temp.url.split("?", 1)[0]
        assert httpx.get(unsigned, timeout=20).status_code == 403, "bucket/object must not be public"
        signed = httpx.get(temp.url, timeout=20)
        assert signed.status_code == 200 and signed.content == b"SYNTHETIC TEST DATA"
    finally:
        storage.delete(temp.key)
    assert httpx.get(temp.url, timeout=20).status_code == 404


@pytest.mark.real_ocr
@pytest.mark.real_oss
@pytest.mark.parametrize("name", ["图片示例.png", "PDF 示例账单2.pdf"])
def test_real_ocr_on_samples_via_oss(settings, name):
    """Recruiter samples contain customer/bank data — require explicit authorization."""
    import os
    if os.getenv("AUTHORIZE_SAMPLE_OCR", "").strip() not in {"1", "true", "yes"}:
        pytest.skip(
            "BLOCKED: recruiter sample OCR upload not authorized. "
            "Synthetic OSS→OCR path is tested separately. "
            "Set AUTHORIZE_SAMPLE_OCR=1 only after confirming data-use permission."
        )
    _require_oss(settings)
    ctx = ParseContext(ocr_service=OcrService.from_settings(settings))
    doc = parse_path(SAMPLES_DIR / name, ctx)
    assert doc.ocr.status == OcrStatus.SUCCESS, doc.ocr.error_message
    assert doc.blocks_by_origin(SourceOrigin.OCR_API)
