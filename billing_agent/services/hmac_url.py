"""HMAC short-lived download URLs shared with workers/ocr-file-proxy.

Contract (must match Worker byte-for-byte):
  message = f"{key}\\n{exp}" where exp is decimal Unix seconds (no leading zeros)
  sig     = hex(HMAC_SHA256(secret, message))   # lowercase hex
  path    = "/o/" + quote(key, safe="/")         # slash-preserving; CF decodes %2F→/
  url     = f"{base}/o/{quote(key, safe='/')}?exp={exp}&sig={sig}"
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote, urlencode


ALLOWED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")


def normalize_prefix(prefix: str) -> str:
    p = (prefix or "ocr-tmp/").strip().lstrip("/")
    if not p.endswith("/"):
        p += "/"
    return p


def is_safe_object_key(key: str, *, prefix: str = "ocr-tmp/") -> bool:
    """Reject path traversal and keys outside the allowed prefix/suffix set."""
    if not key or not isinstance(key, str):
        return False
    if "\\" in key or key.startswith("/") or ".." in key.split("/"):
        return False
    if any(part == "" or part in {".", ".."} for part in key.split("/")):
        return False
    pref = normalize_prefix(prefix)
    if not key.startswith(pref):
        return False
    lower = key.lower()
    return any(lower.endswith(sfx) for sfx in ALLOWED_SUFFIXES)


def sign_message(key: str, exp: int) -> str:
    return f"{key}\n{exp}"


def compute_sig(secret: str, key: str, exp: int) -> str:
    msg = sign_message(key, exp).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_sig(secret: str, key: str, exp: int, sig: str, *, now: int | None = None) -> str | None:
    """Return None if valid; otherwise a short reason code."""
    if not sig or not isinstance(sig, str):
        return "missing_sig"
    if not re_fullmatch_hex(sig):
        return "bad_sig_format"
    try:
        exp_i = int(exp)
    except (TypeError, ValueError):
        return "bad_exp"
    current = int(time.time() if now is None else now)
    if exp_i < current:
        return "expired"
    expected = compute_sig(secret, key, exp_i)
    if not hmac.compare_digest(expected, sig.lower()):
        return "bad_sig"
    return None


def re_fullmatch_hex(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def encode_key_path(key: str) -> str:
    """Path encoding compatible with Worker: encodeURIComponent per segment, keep '/'."""
    return quote(key, safe="/")


def build_signed_get_url(base_url: str, key: str, *, secret: str, exp: int) -> str:
    base = base_url.rstrip("/")
    path = f"/o/{encode_key_path(key)}"
    query = urlencode({"exp": str(exp), "sig": compute_sig(secret, key, exp)})
    return f"{base}{path}?{query}"
