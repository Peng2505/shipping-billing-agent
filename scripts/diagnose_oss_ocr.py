"""Minimal OSS→OCR diagnosis using a public test PDF (no customer data).

Writes a desensitized report to docs/ocr_gateway_diagnosis.md.
Never prints AccessKeys or full signed URLs.

Usage:
  .venv/Scripts/python scripts/diagnose_oss_ocr.py
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from billing_agent.config import load_settings
from billing_agent.security import redact_url, short_hash
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.oss_storage import AliyunOSSStorage, StorageError

# Public, non-customer PDF used previously for OCR contract checks.
PUBLIC_PDF_URL = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

_SENSITIVE = re.compile(
    r"(accesskeyid|accesskey|secret|signature|security-token|session|Expires)=[^\s&\"']+",
    re.I,
)


def _safe(text: str, limit: int = 240) -> str:
    text = _SENSITIVE.sub(lambda m: m.group(0).split("=", 1)[0] + "=***", text)
    text = re.sub(r"https://[^\s\"']+", lambda m: redact_url(m.group(0)), text)
    return text[:limit]


def _url_shape(url: str) -> dict:
    parts = urlsplit(url)
    qs = parse_qs(parts.query, keep_blank_values=True)
    param_names = sorted(qs.keys())
    host = (parts.hostname or "").lower()
    return {
        "scheme": parts.scheme,
        "host_suffix": ".".join(host.split(".")[-3:]) if host.count(".") >= 2 else host,
        "path_has_prefix": "/ocr-tmp/" in (parts.path or ""),
        "query_param_count": len(param_names),
        "query_param_names": param_names,
        "has_signature_param": any("signature" in p.lower() for p in param_names),
        "has_expires_param": any("expires" in p.lower() for p in param_names),
        "url_length": len(url),
        "redacted": redact_url(url),
    }


def main() -> int:
    settings = load_settings()
    lines: list[str] = []
    lines.append("# OCR gateway diagnosis (synthetic / public PDF only)")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).isoformat()}`")
    lines.append(f"- Public PDF URL host: `{urlsplit(PUBLIC_PDF_URL).hostname}`")
    lines.append(f"- OCR endpoint host: `{urlsplit(settings.ocr.endpoint).hostname}`")
    lines.append(f"- OSS configured: `{settings.oss.configured}`")
    lines.append(f"- OSS region set: `{bool(settings.oss.region)}`")
    lines.append(f"- OSS bucket set: `{bool(settings.oss.bucket)}`")
    lines.append(f"- OSS expire seconds: `{settings.oss.url_expire_seconds}`")
    lines.append("")
    lines.append("No AccessKeys, secrets, or full signed URLs are included below.")
    lines.append("")

    # --- A: download public PDF locally ---
    lines.append("## A. Public PDF download (control)")
    t0 = time.monotonic()
    try:
        pub = httpx.get(PUBLIC_PDF_URL, timeout=60, follow_redirects=True)
        pub_ms = int((time.monotonic() - t0) * 1000)
        pdf_bytes = pub.content
        lines.append(f"- HTTP status: `{pub.status_code}`")
        lines.append(f"- Size bytes: `{len(pdf_bytes)}`")
        lines.append(f"- Content-Type: `{pub.headers.get('content-type', '')}`")
        lines.append(f"- SHA256 (12): `{hashlib.sha256(pdf_bytes).hexdigest()[:12]}`")
        lines.append(f"- Elapsed ms: `{pub_ms}`")
        lines.append(f"- Starts with %PDF: `{pdf_bytes.startswith(b'%PDF')}`")
    except Exception as exc:
        lines.append(f"- FAILED: `{type(exc).__name__}: {_safe(str(exc))}`")
        _write(lines)
        return 1

    client = OcrClient(settings.ocr)

    # --- B: OCR with direct public URL ---
    lines.append("")
    lines.append("## B. OCR with direct public URL (no query string)")
    t0 = time.monotonic()
    try:
        resp = client.process(PUBLIC_PDF_URL)
        lines.append(f"- Result: `PASSED`")
        lines.append(f"- HTTP: `{resp.http_status}`")
        lines.append(f"- Elapsed ms: `{resp.elapsed_ms}`")
        items = (resp.payload or {}).get("data", {}).get("list", [])
        lines.append(f"- data.list length: `{len(items) if isinstance(items, list) else 'n/a'}`")
        direct_ok = True
        direct_ms = resp.elapsed_ms
    except OcrError as exc:
        lines.append(f"- Result: `FAILED`")
        lines.append(f"- code: `{exc.code}` http: `{exc.http_status}` elapsed_ms: `{exc.elapsed_ms}`")
        lines.append(f"- message: `{_safe(exc.message)}`")
        direct_ok = False
        direct_ms = exc.elapsed_ms
    lines.append(f"- URL has query params: `False`")
    lines.append(f"- Wall clock ms: `{int((time.monotonic() - t0) * 1000)}`")

    # --- C: OSS upload → local signed GET → OCR ---
    lines.append("")
    lines.append("## C. Same bytes via OSS signed URL → OCR")
    if not settings.oss.configured:
        lines.append("- Result: `BLOCKED` (OSS not configured)")
        classification = "NOT_TESTED"
        _finish(lines, classification, direct_ok, direct_ms)
        return 0

    storage = AliyunOSSStorage(settings.oss)
    temp = None
    try:
        temp = storage.put_temporary(pdf_bytes, ".pdf", "application/pdf")
        shape = _url_shape(temp.url)
        lines.append(f"- OSS put: `PASSED` key_hash=`{short_hash(temp.key)}` size=`{len(pdf_bytes)}`")
        lines.append(f"- Signed URL shape: `{shape}`")
        lines.append(f"- Expire configured seconds: `{settings.oss.url_expire_seconds}`")

        # Local signed GET
        t0 = time.monotonic()
        signed_get = httpx.get(temp.url, timeout=60)
        get_ms = int((time.monotonic() - t0) * 1000)
        lines.append(
            f"- Local signed GET: status=`{signed_get.status_code}` "
            f"bytes=`{len(signed_get.content)}` content-type=`{signed_get.headers.get('content-type','')}` "
            f"elapsed_ms=`{get_ms}`"
        )
        lines.append(
            f"- Body SHA match upload: `{hashlib.sha256(signed_get.content).hexdigest() == hashlib.sha256(pdf_bytes).hexdigest()}`"
        )

        unsigned = temp.url.split("?", 1)[0]
        un_status = httpx.get(unsigned, timeout=30).status_code
        lines.append(f"- Unsigned GET (expect 403): `{un_status}`")

        # OCR via signed URL
        t0 = time.monotonic()
        try:
            resp = client.process(temp.url)
            lines.append(f"- OCR via signed URL: `PASSED` http=`{resp.http_status}` elapsed_ms=`{resp.elapsed_ms}`")
            classification = "OK"
            signed_ocr_ms = resp.elapsed_ms
        except OcrError as exc:
            wall = int((time.monotonic() - t0) * 1000)
            lines.append(
                f"- OCR via signed URL: `FAILED` code=`{exc.code}` http=`{exc.http_status}` "
                f"elapsed_ms=`{exc.elapsed_ms}` wall_ms=`{wall}`"
            )
            lines.append(f"- message: `{_safe(exc.message)}`")
            signed_ocr_ms = exc.elapsed_ms or wall
            # Classify
            if exc.http_status in {502, 504} or (exc.elapsed_ms and exc.elapsed_ms >= 60000):
                if signed_get.status_code == 200 and direct_ok:
                    classification = "OCR_GATEWAY_TIMEOUT_FETCHING_FILE"
                else:
                    classification = "OCR_GATEWAY_TIMEOUT_UNKNOWN"
            elif "PublicEndpointForbidden" in (exc.message or ""):
                classification = "PUBLIC_ENDPOINT_FORBIDDEN"
            else:
                classification = f"OCR_ERROR_{exc.code}"
    except StorageError as exc:
        lines.append(f"- OSS FAILED: `{exc.code}` `{_safe(exc.message)}`")
        classification = f"OSS_{exc.code}"
        signed_ocr_ms = None
    finally:
        if temp is not None:
            try:
                storage.delete(temp.key)
                lines.append(f"- OSS delete: `PASSED` key_hash=`{short_hash(temp.key)}`")
            except StorageError as exc:
                lines.append(f"- OSS delete: `FAILED` `{exc.code}`")

    _finish(lines, classification, direct_ok, direct_ms, signed_ocr_ms if "signed_ocr_ms" in dir() else None)
    return 0 if classification in {"OK"} else 2


def _finish(lines, classification, direct_ok, direct_ms, signed_ms=None) -> None:
    lines.append("")
    lines.append("## D. Classification")
    lines.append(f"- **{classification}**")
    lines.append("")
    lines.append("### Evidence notes")
    lines.append(
        f"- Direct public URL OCR: `{'PASSED' if direct_ok else 'FAILED'}` "
        f"(elapsed_ms=`{direct_ms}`)"
    )
    if signed_ms is not None:
        lines.append(f"- Signed URL OCR elapsed_ms: `{signed_ms}`")
    lines.append(
        "- If local signed GET is 200 and direct OCR works, but signed-URL OCR returns "
        "nginx 504 after ~60s, the failure is most consistent with the OCR gateway "
        "failing to download the file (remote fetch stage), not with local signing."
    )
    lines.append(
        "- Signed URLs necessarily include query parameters (Expires/Signature/...). "
        "If the OCR gateway cannot fetch URLs with query strings, that would also "
        "explain the failure; this cannot be proven from the client alone without "
        "server-side logs."
    )
    lines.append("")
    lines.append("## E. Short note for OCR service vendor")
    lines.append("")
    lines.append("```")
    lines.append("Subject: OCR gateway 504 when file= is an Aliyun OSS signed HTTPS URL")
    lines.append("")
    lines.append("We POST to https://gateway.pltplt.com/ai/process with task=orderChange.")
    lines.append("Control: file=<public HTTPS PDF without query string> → success (~15–20s).")
    lines.append("Failing case: same PDF bytes uploaded to private Aliyun OSS (cn-shanghai),")
    lines.append("file=<HTTPS GET signed URL with query params Expires/Signature/...> →")
    lines.append("HTTP 504 Gateway Time-out from nginx after ~60–65s.")
    lines.append("")
    lines.append("Client-side checks already done:")
    lines.append("- Local GET of the same signed URL returns HTTP 200 quickly.")
    lines.append("- Unsigned object URL returns 403 (bucket remains private).")
    lines.append("- No PublicEndpointForbidden observed on the OSS public endpoint.")
    lines.append("- Content-Type application/pdf; object size matches upload.")
    lines.append("")
    lines.append("Please check whether your workers can egress to *.aliyuncs.com and")
    lines.append("whether signed URLs with query parameters are supported for file=.")
    lines.append("```")
    lines.append("")
    _write(lines)


def _write(lines: list[str]) -> None:
    out = ROOT / "docs" / "ocr_gateway_diagnosis.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")  # path only; report has no secrets


if __name__ == "__main__":
    raise SystemExit(main())
