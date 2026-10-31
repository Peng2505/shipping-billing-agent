"""CloudflareR2WorkerProvider + factory — MockTransport only (no real Cloudflare)."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from billing_agent.config import (
    OssSettings,
    R2WorkerSettings,
    Settings,
)
from billing_agent.services.file_url_factory import (
    PROVIDER_ALIYUN_OSS,
    PROVIDER_CLOUDFLARE_R2_WORKER,
    create_file_url_provider,
)
from billing_agent.services.hmac_url import compute_sig, verify_sig
from billing_agent.services.oss_storage import StorageError
from billing_agent.services.r2_worker_storage import CloudflareR2WorkerProvider


def _r2_settings(**kwargs) -> R2WorkerSettings:
    base = dict(
        base_url="https://ocr-file-proxy.example.workers.dev",
        upload_token="upload-token-test",
        hmac_secret="hmac-secret-test",
        key_prefix="ocr-tmp/",
        url_expire_seconds=1800,
        max_upload_bytes=1024 * 1024,
    )
    base.update(kwargs)
    return R2WorkerSettings(**base)


def test_put_temporary_signs_url_and_uses_bearer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["ct"] = request.headers.get("Content-Type")
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    provider = CloudflareR2WorkerProvider(
        _r2_settings(),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    temp = provider.put_temporary(b"%PDF-1.4 synth", ".pdf", "application/pdf")

    assert seen["method"] == "PUT"
    assert seen["auth"] == "Bearer upload-token-test"
    assert seen["ct"] == "application/pdf"
    assert seen["body"] == b"%PDF-1.4 synth"
    assert "/admin/objects/ocr-tmp/" in seen["url"]

    parts = urlsplit(temp.url)
    assert parts.scheme == "https"
    assert parts.path.startswith("/o/ocr-tmp/")
    qs = parse_qs(parts.query)
    exp = int(qs["exp"][0])
    sig = qs["sig"][0]
    assert verify_sig(_r2_settings().hmac_secret, temp.key, exp, sig, now=exp - 10) is None
    assert compute_sig(_r2_settings().hmac_secret, temp.key, exp) == sig
    assert temp.expires_at > datetime.now(timezone.utc)


def test_delete_requires_bearer_and_accepts_404():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer upload-token-test"
        return httpx.Response(404, json={"error": "not_found"})

    provider = CloudflareR2WorkerProvider(
        _r2_settings(),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.delete("ocr-tmp/20261030/deadbeef.pdf")


def test_upload_http_error_maps_to_storage_error():
    provider = CloudflareR2WorkerProvider(
        _r2_settings(),
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no"))),
    )
    with pytest.raises(StorageError) as ei:
        provider.put_temporary(b"x", ".pdf", "application/pdf")
    assert ei.value.code == "UPLOAD_FAILED"


def test_too_large_rejected_locally():
    provider = CloudflareR2WorkerProvider(
        _r2_settings(max_upload_bytes=4),
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    with pytest.raises(StorageError) as ei:
        provider.put_temporary(b"12345", ".pdf", "application/pdf")
    assert ei.value.code == "TOO_LARGE"


def test_factory_selects_r2_when_requested(monkeypatch):
    settings = Settings(
        file_url_provider=PROVIDER_CLOUDFLARE_R2_WORKER,
        r2_worker=_r2_settings(),
        oss=OssSettings(),
    )
    provider = create_file_url_provider(settings)
    assert provider is not None
    assert provider.name == "cloudflare_r2_worker"


def test_factory_selects_oss_when_requested():
    settings = Settings(
        file_url_provider=PROVIDER_ALIYUN_OSS,
        r2_worker=R2WorkerSettings(),
        oss=OssSettings(
            endpoint="https://oss-cn-shanghai.aliyuncs.com",
            region="cn-shanghai",
            bucket="shipping-billing-test",
            access_key_id="id",
            access_key_secret="secret",
        ),
    )
    # Construction should not hit the network; only validates client wiring.
    provider = create_file_url_provider(settings)
    assert provider is not None
    assert provider.name == "aliyun_oss"


def test_factory_auto_prefers_r2_when_only_r2_configured():
    settings = Settings(
        file_url_provider="",
        r2_worker=_r2_settings(),
        oss=OssSettings(),
    )
    provider = create_file_url_provider(settings)
    assert provider is not None and provider.name == "cloudflare_r2_worker"


def test_factory_r2_missing_returns_none():
    settings = Settings(
        file_url_provider=PROVIDER_CLOUDFLARE_R2_WORKER,
        r2_worker=R2WorkerSettings(base_url="https://x.workers.dev"),
    )
    assert create_file_url_provider(settings) is None
