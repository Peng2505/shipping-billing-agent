"""Upload -> signed URL -> OCR -> cleanup orchestration.

Returns an OcrOutcome in every case. A failure is reported as FAILED or
NOT_CONFIGURED and is never replaced with text from another source.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from billing_agent.config import Settings
from billing_agent.schemas import OcrOutcome, OcrStatus
from billing_agent.security import short_hash
from billing_agent.services.file_url_factory import create_file_url_provider
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.oss_storage import FileUrlProvider, StorageError

logger = logging.getLogger(__name__)

SIGNED_URL_SAFETY_MARGIN = timedelta(seconds=60)

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def content_type_for(suffix: str) -> str:
    return _CONTENT_TYPES.get(suffix.lower(), "application/octet-stream")


def assess_payload(payload: dict[str, Any]) -> list[str]:
    """Recognition-quality warnings derived only from observed response fields."""
    warnings: list[str] = []
    items = payload.get("data", {}).get("list", [])
    if not items:
        warnings.append("OCR returned an empty data.list")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"OCR data.list[{idx}] is not an object")
            continue
        if str(item.get("suspicious", "")).upper() not in {"", "N"}:
            warnings.append(f"OCR data.list[{idx}].suspicious={item.get('suspicious')!r}")
        has_content = any(
            (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v)
            for k, v in item.items()
            if k not in {"fileType", "suspicious", "isDetention", "isDemurrage", "page_index"}
        )
        if not has_content:
            warnings.append(f"OCR data.list[{idx}] contains no recognised business fields")
    return warnings


class OcrService:
    def __init__(
        self,
        client: OcrClient,
        url_provider: FileUrlProvider | None,
        *,
        disabled_reason: str | None = None,
    ) -> None:
        self.client = client
        self.url_provider = url_provider
        # "not_authorized" = operator did not enable OCR for this run (not a storage misconfig).
        self.disabled_reason = disabled_reason

    @classmethod
    def from_settings(cls, settings: Settings) -> OcrService:
        provider = create_file_url_provider(settings)
        return cls(OcrClient(settings.ocr), provider)

    @property
    def configured(self) -> bool:
        return self.url_provider is not None

    def _base(self, status: OcrStatus, **kwargs: Any) -> OcrOutcome:
        return OcrOutcome(
            status=status,
            endpoint=self.client.settings.endpoint,
            task=self.client.settings.task,
            task_type=self.client.settings.task_type,
            storage_provider=getattr(self.url_provider, "name", None),
            requested_at=datetime.now(timezone.utc),
            **kwargs,
        )

    def recognize(self, data: bytes, suffix: str) -> OcrOutcome:
        if self.disabled_reason == "not_authorized":
            return self._base(
                OcrStatus.NOT_APPLICABLE,
                error_code="OCR_NOT_AUTHORIZED",
                error_message=(
                    "OCR upload was not authorized for this run; OCR was not called. "
                    "PDF text_layer (if any) may still be used."
                ),
            )
        if self.url_provider is None:
            return self._base(
                OcrStatus.NOT_CONFIGURED,
                error_code="STORAGE_NOT_CONFIGURED",
                error_message=(
                    "No file URL provider configured (set FILE_URL_PROVIDER to "
                    "local_tunnel, cloudflare_r2_worker, or aliyun_oss with matching "
                    "credentials); OCR was not called."
                ),
            )

        try:
            temp = self.url_provider.put_temporary(data, suffix, content_type_for(suffix))
        except StorageError as exc:
            return self._base(OcrStatus.FAILED, error_code=exc.code, error_message=exc.message)

        outcome: OcrOutcome
        try:
            if datetime.now(timezone.utc) + SIGNED_URL_SAFETY_MARGIN >= temp.expires_at:
                outcome = self._base(OcrStatus.FAILED, error_code="SIGNED_URL_EXPIRED",
                                     error_message="Signed URL expired before the OCR call")
            else:
                response = self.client.process(temp.url)
                outcome = self._base(
                    OcrStatus.SUCCESS,
                    http_status=response.http_status,
                    elapsed_ms=response.elapsed_ms,
                    raw_response=response.payload,
                    warnings=assess_payload(response.payload),
                )
        except OcrError as exc:
            outcome = self._base(
                OcrStatus.FAILED,
                http_status=exc.http_status,
                elapsed_ms=exc.elapsed_ms,
                error_code=exc.code,
                error_message=exc.message,
            )
        finally:
            key_hash = short_hash(temp.key)
            try:
                self.url_provider.delete(temp.key)
                cleanup_warning = None
            except StorageError as exc:
                cleanup_warning = (
                    f"Temporary object key#{key_hash} was not deleted ({exc.code}); "
                    "the bucket lifecycle rule must remove it."
                )
                logger.warning(cleanup_warning)

        outcome.object_key_hash = key_hash
        if cleanup_warning:
            outcome.warnings.append(cleanup_warning)
        return outcome
