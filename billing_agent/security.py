"""Input hardening helpers: file names, size limits, remote URL checks, log redaction."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit

_RESERVED_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_FILENAME_LENGTH = 180


class SecurityError(ValueError):
    """Raised when an input violates a safety rule."""


def sanitize_filename(name: str | None, fallback: str = "unnamed") -> str:
    """Return a display/storage-safe base name. Never returns a path."""
    if not name:
        return fallback
    name = unicodedata.normalize("NFC", str(name))
    name = re.sub(r"[^\S\r\n]", " ", name)  # NBSP and other unicode spaces -> plain space
    name = re.split(r"[\\/]", name)[-1]
    name = _RESERVED_CHARS.sub("_", name)
    name = name.strip().strip(".").strip()
    if not name:
        return fallback
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    ext = ext[:16]
    max_stem = MAX_FILENAME_LENGTH - (len(ext) + 1 if ext else 0)
    stem = stem[:max_stem] or fallback
    return f"{stem}.{ext}" if ext else stem


def file_extension(name: str) -> str:
    _, dot, ext = name.rpartition(".")
    return ext.lower() if dot else ""


def check_size(size: int, limit: int, label: str) -> None:
    if size > limit:
        raise SecurityError(f"{label} exceeds the size limit ({size} > {limit} bytes)")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_WINDOWS_PATH = re.compile(r"^[a-zA-Z]:[\\/]")


def validate_remote_file_url(url: str) -> str:
    """Accept only public https URLs. Rejects local paths, file://, localhost and private IPs."""
    if not isinstance(url, str) or not url.strip():
        raise SecurityError("file URL is empty")
    url = url.strip()
    if _WINDOWS_PATH.match(url) or url.startswith(("/", "\\", "./", "../", "~")):
        raise SecurityError("a local file path is not a remote URL")
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise SecurityError("only https URLs are allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise SecurityError("URL has no host")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
        raise SecurityError("URL points to a local host")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    ):
        raise SecurityError("URL points to a non-public IP address")
    return url


def redact_url(url: str) -> str:
    """Loggable form of a (possibly signed) URL: host + short hash of the rest."""
    parts = urlsplit(url)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{parts.scheme}://{parts.hostname}/<redacted:{digest}>"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


_LONG_DIGITS = re.compile(r"\d[\d -]{7,}\d")
_SECRET_QUERY = re.compile(r"(?i)(signature|accesskeyid|security-token|x-oss-[a-z-]+)=[^&\s]+")


def redact_text(text: str) -> str:
    """Mask long digit runs (account numbers) and URL signature parameters for logs."""
    text = _SECRET_QUERY.sub(lambda m: f"{m.group(1)}=***", text)
    return _LONG_DIGITS.sub(lambda m: m.group(0)[:2] + "***" + m.group(0)[-2:], text)
