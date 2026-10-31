"""HTTP client for the assignment OCR API (https://gateway.pltplt.com/ai/process).

Only the parts of the response contract that were observed in real calls are
validated here (see docs/assumptions.md section 3.1). Field-level business
mapping is intentionally not done in this module.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from billing_agent.config import OcrSettings
from billing_agent.security import SecurityError, redact_url, validate_remote_file_url

logger = logging.getLogger(__name__)


class OcrError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int | None = None,
                 elapsed_ms: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.elapsed_ms = elapsed_ms


@dataclass(frozen=True)
class OcrResponse:
    http_status: int
    elapsed_ms: int
    payload: dict[str, Any]


def _snippet(text: str, limit: int = 200) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class OcrClient:
    def __init__(self, settings: OcrSettings, http: httpx.Client | None = None) -> None:
        self.settings = settings
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.connect_timeout,
                read=settings.read_timeout,
                write=30.0,
                pool=10.0,
            )
        )

    def build_request(self, file_url: str) -> dict[str, str]:
        return {
            "file": file_url,
            "task": self.settings.task,
            "callBack": self.settings.callback,
            "taskType": self.settings.task_type,
        }

    def process(self, file_url: str) -> OcrResponse:
        try:
            validate_remote_file_url(file_url)
        except SecurityError as exc:
            raise OcrError("INVALID_URL", str(exc)) from exc

        started = time.monotonic()
        try:
            response = self._http.post(self.settings.endpoint, json=self.build_request(file_url))
        except httpx.TimeoutException as exc:
            raise OcrError("TIMEOUT", f"OCR request timed out: {type(exc).__name__}",
                           elapsed_ms=_ms(started)) from exc
        except httpx.TransportError as exc:
            raise OcrError("NETWORK_ERROR", f"OCR request failed: {type(exc).__name__}",
                           elapsed_ms=_ms(started)) from exc
        elapsed = _ms(started)
        logger.info("OCR POST %s -> %s in %d ms", redact_url(file_url), response.status_code, elapsed)

        if response.status_code != 200:
            raise OcrError(
                "HTTP_ERROR",
                f"OCR HTTP {response.status_code}: {_snippet(response.text)}",
                http_status=response.status_code,
                elapsed_ms=elapsed,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OcrError("INVALID_RESPONSE", f"OCR response is not JSON: {_snippet(response.text)}",
                           http_status=200, elapsed_ms=elapsed) from exc
        if not isinstance(payload, dict):
            raise OcrError("UNEXPECTED_SCHEMA", "OCR response top level is not an object",
                           http_status=200, elapsed_ms=elapsed)
        if payload.get("success") is not True:
            raise OcrError(
                "OCR_REPORTED_FAILURE",
                f"OCR success={payload.get('success')!r} error_code={payload.get('error_code')!r} "
                f"message={str(payload.get('message'))[:200]!r}",
                http_status=200,
                elapsed_ms=elapsed,
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise OcrError("UNEXPECTED_SCHEMA", "OCR response has no data.list array",
                           http_status=200, elapsed_ms=elapsed)
        return OcrResponse(http_status=200, elapsed_ms=elapsed, payload=payload)

    def close(self) -> None:
        self._http.close()


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
