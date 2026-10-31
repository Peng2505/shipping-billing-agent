"""Security checks for R2 Worker URL/key contract (local, no Cloudflare deploy)."""

from __future__ import annotations

import httpx
import pytest

from billing_agent.config import R2WorkerSettings
from billing_agent.services.hmac_url import (
    build_signed_get_url,
    compute_sig,
    is_safe_object_key,
    verify_sig,
)
from billing_agent.services.oss_storage import StorageError
from billing_agent.services.r2_worker_storage import CloudflareR2WorkerProvider


def _settings() -> R2WorkerSettings:
    return R2WorkerSettings(
        base_url="https://ocr-file-proxy.example.workers.dev",
        upload_token="tok",
        hmac_secret="sec",
        key_prefix="ocr-tmp/",
    )


@pytest.mark.parametrize(
    "key",
    [
        "../ocr-tmp/x.pdf",
        "ocr-tmp/../x.pdf",
        "ocr-tmp//x.pdf",
        "ocr-tmp/./x.pdf",
        "/ocr-tmp/x.pdf",
        "ocr-tmp/x.pdf/../y.pdf",
        "ocr-tmp/x.exe",
        "tmp/x.pdf",
    ],
)
def test_path_traversal_and_suffix_rejected(key: str):
    assert not is_safe_object_key(key, prefix="ocr-tmp/")


def test_provider_rejects_unsafe_delete_key():
    provider = CloudflareR2WorkerProvider(
        _settings(),
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    with pytest.raises(StorageError) as ei:
        provider.delete("ocr-tmp/../secret.pdf")
    assert ei.value.code == "INVALID_KEY"


def test_wrong_signature_and_expired_urls():
    key = "ocr-tmp/20261030/safe.pdf"
    exp = 1_900_000_000
    good = build_signed_get_url("https://example.workers.dev", key, secret="sec", exp=exp)
    assert "sig=" in good
    sig = compute_sig("sec", key, exp)
    assert verify_sig("sec", key, exp, sig, now=exp - 1) is None
    assert verify_sig("sec", key, exp, sig, now=exp + 100) == "expired"
    assert verify_sig("sec", key, exp, "ff" * 32, now=exp - 1) == "bad_sig"
    # Wrong secret
    assert verify_sig("other", key, exp, sig, now=exp - 1) == "bad_sig"


def test_unauthorized_upload_surfaces_as_upload_failed():
    provider = CloudflareR2WorkerProvider(
        _settings(),
        http=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "unauthorized"}))
        ),
    )
    with pytest.raises(StorageError) as ei:
        provider.put_temporary(b"%PDF", ".pdf", "application/pdf")
    assert ei.value.code == "UPLOAD_FAILED"
