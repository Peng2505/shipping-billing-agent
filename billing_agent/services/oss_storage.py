"""Aliyun OSS adapter that turns local bytes into a short-lived signed HTTPS URL.

The bucket must stay private. Objects are written with a private ACL and
`x-oss-forbid-overwrite`, removed after OCR, and should also be covered by a
bucket lifecycle rule on the configured prefix as a safety net.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from billing_agent.config import OssSettings
from billing_agent.security import short_hash

logger = logging.getLogger(__name__)

_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$")


class StorageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TempObject:
    key: str
    url: str
    expires_at: datetime


class FileUrlProvider(Protocol):
    name: str

    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject: ...

    def delete(self, key: str) -> None: ...


def build_object_key(prefix: str, suffix: str, now: datetime | None = None) -> str:
    suffix = suffix.lower()
    if not _SAFE_SUFFIX.match(suffix):
        suffix = ".bin"
    now = now or datetime.now(timezone.utc)
    prefix = prefix.strip("/")
    return f"{prefix}/{now:%Y%m%d}/{uuid.uuid4().hex}{suffix}"


class AliyunOSSStorage:
    name = "aliyun_oss"

    def __init__(self, settings: OssSettings, bucket: Any | None = None) -> None:
        if bucket is None and not settings.configured:
            raise StorageError("NOT_CONFIGURED", f"OSS missing: {', '.join(settings.missing_fields())}")
        self.settings = settings
        self._bucket = bucket or self._create_bucket(settings)

    @staticmethod
    def _create_bucket(settings: OssSettings) -> Any:
        import oss2
        from oss2.credentials import StaticCredentialsProvider

        provider = StaticCredentialsProvider(
            settings.access_key_id, settings.access_key_secret, settings.session_token
        )
        if settings.region:
            auth = oss2.ProviderAuthV4(provider)
            return oss2.Bucket(auth, settings.endpoint, settings.bucket, region=settings.region)
        auth = oss2.ProviderAuth(provider)
        return oss2.Bucket(auth, settings.endpoint, settings.bucket)

    @classmethod
    def from_settings(cls, settings: OssSettings) -> AliyunOSSStorage | None:
        return cls(settings) if settings.configured else None

    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject:
        key = build_object_key(self.settings.prefix, suffix)
        headers = {
            "Content-Type": content_type or "application/octet-stream",
            "x-oss-object-acl": "private",
            "x-oss-forbid-overwrite": "true",
        }
        try:
            self._bucket.put_object(key, data, headers=headers)
        except Exception as exc:  # oss2 raises many exception types
            raise StorageError("UPLOAD_FAILED", f"OSS upload failed: {type(exc).__name__}") from exc
        expires = self.settings.url_expire_seconds
        try:
            url = self._bucket.sign_url("GET", key, expires, slash_safe=True)
        except Exception as exc:
            self.delete(key)
            raise StorageError("SIGN_FAILED", f"OSS URL signing failed: {type(exc).__name__}") from exc
        if not url.lower().startswith("https://"):
            self.delete(key)
            raise StorageError("INSECURE_URL", "OSS endpoint must be https so the signed URL is https")
        logger.info("OSS put object key#%s (%d bytes, expires %ds)", short_hash(key), len(data), expires)
        return TempObject(
            key=key,
            url=url,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )

    def delete(self, key: str) -> None:
        try:
            self._bucket.delete_object(key)
        except Exception as exc:
            raise StorageError("DELETE_FAILED", f"OSS delete failed: {type(exc).__name__}") from exc
        logger.info("OSS deleted object key#%s", short_hash(key))
