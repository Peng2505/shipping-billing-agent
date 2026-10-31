"""Cloudflare R2 via Worker admin API + HMAC download URLs (FileUrlProvider)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import httpx

from billing_agent.config import R2WorkerSettings
from billing_agent.security import short_hash
from billing_agent.services.hmac_url import (
    build_signed_get_url,
    encode_key_path,
    is_safe_object_key,
    normalize_prefix,
)
from billing_agent.services.oss_storage import StorageError, TempObject, build_object_key

logger = logging.getLogger(__name__)


class CloudflareR2WorkerProvider:
    name = "cloudflare_r2_worker"

    def __init__(
        self,
        settings: R2WorkerSettings,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        if not settings.configured:
            raise StorageError(
                "NOT_CONFIGURED",
                f"R2 Worker missing: {', '.join(settings.missing_fields())}",
            )
        self.settings = settings
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(connect=15.0, read=120.0, write=120.0, pool=10.0)
        )
        self._owns_http = http is None

    @classmethod
    def from_settings(cls, settings: R2WorkerSettings) -> CloudflareR2WorkerProvider | None:
        return cls(settings) if settings.configured else None

    def _admin_url(self, key: str) -> str:
        if not is_safe_object_key(key, prefix=self.settings.key_prefix):
            raise StorageError("INVALID_KEY", "object key failed safety checks")
        base = self.settings.base_url.rstrip("/")
        return f"{base}/admin/objects/{encode_key_path(key)}"

    def _auth_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.settings.upload_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject:
        if len(data) > self.settings.max_upload_bytes:
            raise StorageError(
                "TOO_LARGE",
                f"upload exceeds max_upload_bytes={self.settings.max_upload_bytes}",
            )
        prefix = normalize_prefix(self.settings.key_prefix)
        key = build_object_key(prefix, suffix)
        if not is_safe_object_key(key, prefix=prefix):
            raise StorageError("INVALID_KEY", "generated key failed safety checks")

        url = self._admin_url(key)
        try:
            response = self._http.put(
                url,
                content=data,
                headers=self._auth_headers(content_type or "application/octet-stream"),
            )
        except httpx.HTTPError as exc:
            raise StorageError("UPLOAD_FAILED", f"R2 Worker upload failed: {type(exc).__name__}") from exc

        if response.status_code not in {200, 201}:
            raise StorageError(
                "UPLOAD_FAILED",
                f"R2 Worker upload HTTP {response.status_code}",
            )

        expires = int(self.settings.url_expire_seconds)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires)
        exp = int(expires_at.timestamp())
        signed = build_signed_get_url(
            self.settings.base_url,
            key,
            secret=self.settings.hmac_secret,
            exp=exp,
        )
        if not signed.lower().startswith("https://"):
            self.delete(key)
            raise StorageError("INSECURE_URL", "R2 Worker base URL must be https")

        logger.info(
            "R2 Worker put object key#%s (%d bytes, expires %ds)",
            short_hash(key),
            len(data),
            expires,
        )
        return TempObject(key=key, url=signed, expires_at=expires_at)

    def delete(self, key: str) -> None:
        url = self._admin_url(key)
        try:
            response = self._http.delete(url, headers=self._auth_headers())
        except httpx.HTTPError as exc:
            raise StorageError("DELETE_FAILED", f"R2 Worker delete failed: {type(exc).__name__}") from exc
        if response.status_code not in {200, 204, 404}:
            raise StorageError(
                "DELETE_FAILED",
                f"R2 Worker delete HTTP {response.status_code}",
            )
        logger.info("R2 Worker deleted object key#%s", short_hash(key))

    def close(self) -> None:
        if self._owns_http:
            self._http.close()
