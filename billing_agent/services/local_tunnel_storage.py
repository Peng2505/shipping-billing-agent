"""LocalTunnelProvider — token files on 127.0.0.1 gateway + Cloudflare Quick Tunnel HTTPS."""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from billing_agent.config import LocalTunnelSettings
from billing_agent.security import short_hash
from billing_agent.services.hmac_url import ALLOWED_SUFFIXES
from billing_agent.services.oss_storage import StorageError, TempObject

logger = logging.getLogger(__name__)


def _suffix_ok(suffix: str) -> bool:
    return suffix.lower() in ALLOWED_SUFFIXES


class LocalTunnelProvider:
    """FileUrlProvider backed by the local tunnel gateway process.

    Requires a running gateway (see scripts/local_tunnel/start_gateway.py).
    Does not silently fall back when the tunnel is down.
    """

    name = "local_tunnel"

    def __init__(
        self,
        settings: LocalTunnelSettings,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        if not settings.configured:
            raise StorageError(
                "NOT_CONFIGURED",
                f"Local tunnel missing: {', '.join(settings.missing_fields())}",
            )
        self.settings = settings
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
        )
        self._owns_http = http is None

    @classmethod
    def from_settings(cls, settings: LocalTunnelSettings) -> LocalTunnelProvider | None:
        return cls(settings) if settings.configured else None

    def _assert_gateway_reachable(self) -> None:
        admin = self.settings.admin_base_url.rstrip("/")
        try:
            r = self._http.get(f"{admin}/health", timeout=5.0)
        except httpx.HTTPError as exc:
            raise StorageError(
                "TUNNEL_UNREACHABLE",
                f"Local tunnel gateway unreachable at {admin}: {type(exc).__name__}. "
                "Run scripts/local_tunnel/start_gateway.py first — no silent OCR fallback.",
            ) from exc
        if r.status_code != 200:
            raise StorageError(
                "TUNNEL_UNREACHABLE",
                f"Local tunnel gateway health HTTP {r.status_code}. "
                "Run scripts/local_tunnel/start_gateway.py first — no silent OCR fallback.",
            )

    def _admin_headers(self, *, access_token: str, expires_at: float, content_type: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.admin_token}",
            "Content-Type": content_type,
            "X-Access-Token": access_token,
            "X-Expires-At": str(int(expires_at)),
        }

    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject:
        if not _suffix_ok(suffix):
            raise StorageError("INVALID_SUFFIX", f"suffix not allowed: {suffix}")
        if len(data) > self.settings.max_upload_bytes:
            raise StorageError(
                "TOO_LARGE",
                f"upload exceeds max_upload_bytes={self.settings.max_upload_bytes}",
            )

        # Refresh public URL from status file if present (tunnel URL changes each start).
        self.settings = self.settings.refresh_from_status_file()
        self._assert_gateway_reachable()
        if not self.settings.public_base_url.startswith("https://"):
            raise StorageError(
                "TUNNEL_UNREACHABLE",
                "Public Tunnel HTTPS URL missing. Is cloudflared running? "
                "Check output/local_tunnel/status.json — no silent OCR fallback.",
            )

        object_id = f"{secrets.token_hex(16)}{suffix.lower()}"
        access_token = secrets.token_urlsafe(24)
        expires = int(self.settings.url_expire_seconds)
        expires_at_ts = time.time() + expires
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires)

        admin = self.settings.admin_base_url.rstrip("/")
        url = f"{admin}/admin/objects/{object_id}"
        try:
            response = self._http.put(
                url,
                content=data,
                headers=self._admin_headers(
                    access_token=access_token,
                    expires_at=expires_at_ts,
                    content_type=content_type or "application/octet-stream",
                ),
            )
        except httpx.HTTPError as exc:
            raise StorageError("UPLOAD_FAILED", f"local tunnel upload failed: {type(exc).__name__}") from exc
        if response.status_code not in {200, 201}:
            raise StorageError("UPLOAD_FAILED", f"local tunnel upload HTTP {response.status_code}")

        public = self.settings.public_base_url.rstrip("/")
        signed = f"{public}/t/{access_token}/{object_id}"
        logger.info(
            "LocalTunnel put object key#%s (%d bytes, expires %ds)",
            short_hash(object_id),
            len(data),
            expires,
        )
        return TempObject(key=object_id, url=signed, expires_at=expires_at)

    def delete(self, key: str) -> None:
        admin = self.settings.admin_base_url.rstrip("/")
        try:
            response = self._http.delete(
                f"{admin}/admin/objects/{key}",
                headers={"Authorization": f"Bearer {self.settings.admin_token}"},
            )
        except httpx.HTTPError as exc:
            raise StorageError("DELETE_FAILED", f"local tunnel delete failed: {type(exc).__name__}") from exc
        if response.status_code not in {200, 204, 404}:
            raise StorageError("DELETE_FAILED", f"local tunnel delete HTTP {response.status_code}")
        logger.info("LocalTunnel deleted object key#%s", short_hash(key))

    def close(self) -> None:
        if self._owns_http:
            self._http.close()
