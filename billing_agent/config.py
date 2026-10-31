"""Runtime configuration loaded from environment variables (.env supported)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OCR_ENDPOINT = "https://gateway.pltplt.com/ai/process"


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number") from exc


@dataclass(frozen=True)
class OcrSettings:
    endpoint: str = DEFAULT_OCR_ENDPOINT
    task: str = "orderChange"
    task_type: str = ""
    callback: str = ""
    connect_timeout: float = 10.0
    read_timeout: float = 300.0


@dataclass(frozen=True)
class OssSettings:
    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key_id: str = field(default="", repr=False)
    access_key_secret: str = field(default="", repr=False)
    session_token: str = field(default="", repr=False)
    prefix: str = "ocr-tmp/"
    url_expire_seconds: int = 1800

    @property
    def configured(self) -> bool:
        return all([self.endpoint, self.bucket, self.access_key_id, self.access_key_secret])

    def missing_fields(self) -> list[str]:
        required = {
            "OSS_ENDPOINT": self.endpoint,
            "OSS_BUCKET": self.bucket,
            "OSS_ACCESS_KEY_ID": self.access_key_id,
            "OSS_ACCESS_KEY_SECRET": self.access_key_secret,
        }
        return [name for name, value in required.items() if not value]


@dataclass(frozen=True)
class R2WorkerSettings:
    """Cloudflare Worker that fronts a private R2 bucket for OCR file= URLs."""

    base_url: str = ""
    upload_token: str = field(default="", repr=False)
    hmac_secret: str = field(default="", repr=False)
    key_prefix: str = "ocr-tmp/"
    url_expire_seconds: int = 1800
    max_upload_bytes: int = 20 * 1024 * 1024

    @property
    def configured(self) -> bool:
        return bool(
            self.base_url.startswith("https://")
            and self.upload_token
            and self.hmac_secret
        )

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.base_url.startswith("https://"):
            missing.append("R2_WORKER_BASE_URL")
        if not self.upload_token:
            missing.append("R2_WORKER_UPLOAD_TOKEN")
        if not self.hmac_secret:
            missing.append("R2_WORKER_HMAC_SECRET")
        return missing


@dataclass(frozen=True)
class LocalTunnelSettings:
    """Cloudflare Quick Tunnel + 127.0.0.1 token file gateway (exam/demo OCR path)."""

    admin_base_url: str = "http://127.0.0.1:8765"
    public_base_url: str = ""
    admin_token: str = field(default="", repr=False)
    status_file: str = ""
    url_expire_seconds: int = 1800
    max_upload_bytes: int = 20 * 1024 * 1024

    @property
    def configured(self) -> bool:
        # Public URL may be filled later from status file; require admin side first.
        return bool(self.admin_base_url.startswith("http://127.0.0.1") and self.admin_token)

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.admin_base_url.startswith("http://127.0.0.1"):
            missing.append("LOCAL_TUNNEL_ADMIN_BASE_URL")
        if not self.admin_token:
            missing.append("LOCAL_TUNNEL_ADMIN_TOKEN")
        return missing

    def refresh_from_status_file(self) -> LocalTunnelSettings:
        """Reload public HTTPS base URL written by start_gateway.py (tunnel URL rotates)."""
        # status_file="-" disables refresh (unit tests).
        if self.status_file.strip() == "-":
            return self
        path = Path(self.status_file) if self.status_file else PROJECT_ROOT / "output" / "local_tunnel" / "status.json"
        if not path.is_file():
            return self
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self
        public = str(data.get("public_base_url") or "").strip().rstrip("/")
        admin = str(data.get("admin_base_url") or self.admin_base_url).strip().rstrip("/")
        token = str(data.get("admin_token") or self.admin_token)
        if not public.startswith("https://"):
            return self
        return LocalTunnelSettings(
            admin_base_url=admin or self.admin_base_url,
            public_base_url=public,
            admin_token=token or self.admin_token,
            status_file=str(path),
            url_expire_seconds=self.url_expire_seconds,
            max_upload_bytes=self.max_upload_bytes,
        )


@dataclass(frozen=True)
class LlmSettings:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""
    temperature: float = 0.0
    timeout: float = 120.0
    # DeepSeek V4/flash enable thinking by default; thinking rejects tool_choice=required.
    # Agent tool calling + ToolStrategy structured output need thinking disabled.
    thinking: str = "disabled"  # disabled | enabled | auto

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


@dataclass(frozen=True)
class LimitSettings:
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 100 * 1024 * 1024
    max_email_depth: int = 3
    max_email_attachments: int = 30


@dataclass(frozen=True)
class Settings:
    ocr: OcrSettings = field(default_factory=OcrSettings)
    oss: OssSettings = field(default_factory=OssSettings)
    r2_worker: R2WorkerSettings = field(default_factory=R2WorkerSettings)
    local_tunnel: LocalTunnelSettings = field(default_factory=LocalTunnelSettings)
    file_url_provider: str = ""  # aliyun_oss | cloudflare_r2_worker | local_tunnel | "" (auto)
    llm: LlmSettings = field(default_factory=LlmSettings)
    limits: LimitSettings = field(default_factory=LimitSettings)
    soffice_path: str = ""


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Read settings from the process environment, optionally loading a .env file first."""
    dotenv_path = Path(env_file) if env_file else PROJECT_ROOT / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path, override=False)

    return Settings(
        ocr=OcrSettings(
            endpoint=_str("OCR_ENDPOINT", DEFAULT_OCR_ENDPOINT) or DEFAULT_OCR_ENDPOINT,
            task=_str("OCR_TASK", "orderChange") or "orderChange",
            task_type=_str("OCR_TASK_TYPE"),
            callback=_str("OCR_CALLBACK"),
            connect_timeout=_float("OCR_CONNECT_TIMEOUT_SECONDS", 10.0),
            read_timeout=_float("OCR_READ_TIMEOUT_SECONDS", 300.0),
        ),
        oss=OssSettings(
            endpoint=_str("OSS_ENDPOINT"),
            region=_str("OSS_REGION"),
            bucket=_str("OSS_BUCKET"),
            access_key_id=_str("OSS_ACCESS_KEY_ID"),
            access_key_secret=_str("OSS_ACCESS_KEY_SECRET"),
            session_token=_str("OSS_SESSION_TOKEN"),
            prefix=_str("OSS_PREFIX", "ocr-tmp/") or "ocr-tmp/",
            url_expire_seconds=_int("OSS_URL_EXPIRE_SECONDS", 1800),
        ),
        r2_worker=R2WorkerSettings(
            base_url=_str("R2_WORKER_BASE_URL"),
            upload_token=_str("R2_WORKER_UPLOAD_TOKEN"),
            hmac_secret=_str("R2_WORKER_HMAC_SECRET"),
            key_prefix=_str("R2_WORKER_KEY_PREFIX", "ocr-tmp/") or "ocr-tmp/",
            url_expire_seconds=_int("R2_WORKER_URL_EXPIRE_SECONDS", 1800),
            max_upload_bytes=_int("R2_WORKER_MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
        ),
        local_tunnel=LocalTunnelSettings(
            admin_base_url=_str("LOCAL_TUNNEL_ADMIN_BASE_URL", "http://127.0.0.1:8765")
            or "http://127.0.0.1:8765",
            public_base_url=_str("LOCAL_TUNNEL_PUBLIC_BASE_URL"),
            admin_token=_str("LOCAL_TUNNEL_ADMIN_TOKEN"),
            status_file=_str(
                "LOCAL_TUNNEL_STATUS_FILE",
                str(PROJECT_ROOT / "output" / "local_tunnel" / "status.json"),
            )
            or str(PROJECT_ROOT / "output" / "local_tunnel" / "status.json"),
            url_expire_seconds=_int("LOCAL_TUNNEL_URL_EXPIRE_SECONDS", 1800),
            max_upload_bytes=_int("LOCAL_TUNNEL_MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
        ),
        file_url_provider=_str("FILE_URL_PROVIDER"),
        llm=LlmSettings(
            base_url=_str("LLM_BASE_URL"),
            api_key=_str("LLM_API_KEY"),
            model=_str("LLM_MODEL"),
            temperature=_float("LLM_TEMPERATURE", 0.0),
            timeout=_float("LLM_TIMEOUT_SECONDS", 120.0),
            thinking=_str("LLM_THINKING", "disabled") or "disabled",
        ),
        limits=LimitSettings(
            max_file_bytes=_int("MAX_FILE_MB", 20) * 1024 * 1024,
            max_total_bytes=_int("MAX_TOTAL_MB", 100) * 1024 * 1024,
            max_email_depth=_int("MAX_EMAIL_DEPTH", 3),
            max_email_attachments=_int("MAX_EMAIL_ATTACHMENTS", 30),
        ),
        soffice_path=_str("SOFFICE_PATH"),
    )
