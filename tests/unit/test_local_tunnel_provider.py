"""LocalTunnelProvider + gateway — in-process, no cloudflared."""

from __future__ import annotations

import time

import httpx
import pytest

from billing_agent.config import LocalTunnelSettings, Settings
from billing_agent.services.file_url_factory import PROVIDER_LOCAL_TUNNEL, create_file_url_provider
from billing_agent.services.local_tunnel_gateway import GatewayState, start_gateway
from billing_agent.services.local_tunnel_storage import LocalTunnelProvider
from billing_agent.services.oss_storage import StorageError


@pytest.fixture()
def gateway():
    token = "test-admin-token-local-tunnel-xx"
    state = GatewayState(admin_token=token, max_upload_bytes=1024 * 1024)
    httpd, _ = start_gateway("127.0.0.1", 0, state)
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            r = httpx.get(f"{base}/health", timeout=0.2)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    yield state, token, base
    httpd.shutdown()


def test_put_get_delete_and_bad_token(gateway):
    _state, admin_token, base = gateway
    settings = LocalTunnelSettings(
        admin_base_url=base,
        public_base_url="https://example.trycloudflare.com",
        admin_token=admin_token,
        status_file="-",
        url_expire_seconds=600,
    )
    provider = LocalTunnelProvider(settings)
    temp = provider.put_temporary(b"%PDF-local-tunnel", ".pdf", "application/pdf")
    assert temp.url.startswith("https://example.trycloudflare.com/t/")
    local_url = temp.url.replace("https://example.trycloudflare.com", base)
    r = httpx.get(local_url, timeout=5)
    assert r.status_code == 200 and r.content == b"%PDF-local-tunnel"

    parts = local_url.split("/")
    parts[-2] = "wrong-token-value-xxx"
    bad = "/".join(parts)
    assert httpx.get(bad, timeout=5).status_code in {401, 403}

    provider.delete(temp.key)
    assert httpx.get(local_url, timeout=5).status_code == 404


def test_unauthorized_admin_put(gateway):
    _state, _admin_token, base = gateway
    r = httpx.put(
        f"{base}/admin/objects/aabbccddeeff0011.pdf",
        content=b"x",
        headers={
            "Content-Type": "application/pdf",
            "X-Access-Token": "tokentokentokentoken",
            "X-Expires-At": str(int(time.time()) + 100),
        },
    )
    assert r.status_code == 401


def test_expired_access_rejected(gateway):
    _state, admin_token, base = gateway
    object_id = "aabbccddeeff00112233aabbccddee.pdf"
    r = httpx.put(
        f"{base}/admin/objects/{object_id}",
        content=b"%PDF",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/pdf",
            "X-Access-Token": "tokentokentokentoken12",
            "X-Expires-At": str(int(time.time()) - 10),
        },
    )
    assert r.status_code == 400


def test_factory_selects_local_tunnel(gateway):
    _state, admin_token, base = gateway
    settings = Settings(
        file_url_provider=PROVIDER_LOCAL_TUNNEL,
        local_tunnel=LocalTunnelSettings(
            admin_base_url=base,
            public_base_url="https://demo.trycloudflare.com",
            admin_token=admin_token,
            status_file="-",
        ),
    )
    p = create_file_url_provider(settings)
    assert p is not None and p.name == "local_tunnel"


def test_unreachable_gateway_fails_loudly():
    settings = LocalTunnelSettings(
        admin_base_url="http://127.0.0.1:59999",
        public_base_url="https://demo.trycloudflare.com",
        admin_token="tok",
        status_file="-",
    )
    provider = LocalTunnelProvider(settings)
    with pytest.raises(StorageError) as ei:
        provider.put_temporary(b"x", ".pdf", "application/pdf")
    assert ei.value.code == "TUNNEL_UNREACHABLE"
