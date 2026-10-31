"""Minimal OSS→OCR 504 probe (synthetic PDF only). Does not change business code.

Writes desensitized evidence to output/oss_ocr_final_probe.txt.
Never prints AccessKeys or full signed URLs.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from billing_agent.config import load_settings
from billing_agent.security import short_hash, validate_remote_file_url
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.oss_storage import AliyunOSSStorage

# Minimal synthetic PDF — no customer content.
SYNTH_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
    b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
    b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
    b"/Contents 4 0 R >>endobj\n"
    b"4 0 obj<< /Length 44 >>stream\n"
    b"BT /F1 12 Tf 50 100 Td (SYNTH) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n"
    b"trailer<< /Size 5 /Root 1 0 R >>\nstartxref\n307\n%%EOF\n"
)

PUBLIC = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
PUBLIC_Q = PUBLIC + "?diag=ossocr1&x=1"


def main() -> int:
    settings = load_settings()
    lines: list[str] = []

    def L(s: str = "") -> None:
        lines.append(s)
        print(s, flush=True)

    L("# OSS->OCR final minimal probe")
    L(f"synthetic_pdf_bytes={len(SYNTH_PDF)} sha12={hashlib.sha256(SYNTH_PDF).hexdigest()[:12]}")
    L(f"ocr_endpoint_host={urlsplit(settings.ocr.endpoint).hostname}")
    L(f"ocr_read_timeout={settings.ocr.read_timeout}")
    L(f"oss_configured={settings.oss.configured} expire_s={settings.oss.url_expire_seconds}")
    L(
        "oss_endpoint_host="
        f"{urlsplit(settings.oss.endpoint).hostname if settings.oss.endpoint else None}"
    )
    L(f"oss_region={settings.oss.region!r} bucket_set={bool(settings.oss.bucket)}")

    if not settings.oss.configured:
        L("BLOCKED: OSS not configured")
        _write(lines)
        return 1

    client = OcrClient(settings.ocr)

    # --- 1) Public OCR control ---
    L("")
    L("## 1. Public URL OCR (no query)")
    t0 = time.monotonic()
    try:
        r = client.process(PUBLIC)
        L(
            f"PASSED http={r.http_status} elapsed_ms={r.elapsed_ms} "
            f"wall={int((time.monotonic() - t0) * 1000)}"
        )
        pub_ok = True
        pub_ms = r.elapsed_ms
    except OcrError as e:
        L(
            f"FAILED code={e.code} http={e.http_status} elapsed_ms={e.elapsed_ms} "
            f"msg={e.message[:160]}"
        )
        pub_ok = False
        pub_ms = e.elapsed_ms

    # --- 2) Public URL + query (query-support probe) ---
    L("")
    L("## 2. Public URL OCR WITH query string (compatibility probe)")
    L(
        f"url_shape host={urlsplit(PUBLIC_Q).hostname} "
        f"query_len={len(urlsplit(PUBLIC_Q).query)} "
        f"params={dict(parse_qsl(urlsplit(PUBLIC_Q).query))}"
    )
    t0 = time.monotonic()
    q_ok = False
    q_ms: int | None = None
    try:
        g = httpx.get(PUBLIC_Q, timeout=60, follow_redirects=True)
        L(
            f"local_GET status={g.status_code} bytes={len(g.content)} "
            f"redirects={len(g.history)} "
            f"final_has_query={bool(urlsplit(str(g.url)).query)} "
            f"ct={g.headers.get('content-type')}"
        )
        r = client.process(PUBLIC_Q)
        L(
            f"OCR PASSED http={r.http_status} elapsed_ms={r.elapsed_ms} "
            f"wall={int((time.monotonic() - t0) * 1000)}"
        )
        q_ok = True
        q_ms = r.elapsed_ms
    except OcrError as e:
        L(
            f"OCR FAILED code={e.code} http={e.http_status} elapsed_ms={e.elapsed_ms} "
            f"wall={int((time.monotonic() - t0) * 1000)} msg={e.message[:200]}"
        )
        q_ms = e.elapsed_ms
    except Exception as e:  # noqa: BLE001 — probe must continue
        L(f"OTHER FAILED {type(e).__name__}: {e}")

    # --- 3) OSS signed URL integrity ---
    L("")
    L("## 3. OSS signed URL integrity (synthetic PDF)")
    storage = AliyunOSSStorage(settings.oss)
    temp = None
    signed_ok = False
    signed_ms: int | None = None
    try:
        temp = storage.put_temporary(SYNTH_PDF, ".pdf", "application/pdf")
        url = temp.url
        parts = urlsplit(url)
        qs = dict(parse_qsl(parts.query, keep_blank_values=True))
        L(f"put_ok key_hash={short_hash(temp.key)} url_len={len(url)} scheme={parts.scheme}")
        host = parts.hostname or ""
        L(f"host_suffix={'.'.join(host.split('.')[-3:]) if host.count('.') >= 2 else host}")
        L(
            f"path_prefix_ok={'/ocr-tmp/' in (parts.path or '')} "
            f"query_param_names={sorted(qs)}"
        )
        L(
            "expires_param="
            f"{qs.get('x-oss-expires') or qs.get('Expires') or qs.get('expires')}"
        )
        L(f"sig_version={qs.get('x-oss-signature-version')}")

        payload = client.build_request(url)
        loaded = json.loads(json.dumps(payload, ensure_ascii=False))
        L(f"json_roundtrip_file_eq_original={loaded.get('file') == url}")
        L(
            "json_body_contains_full_query="
            f"{('?' in (loaded.get('file') or '')) and len(loaded.get('file') or '') == len(url)}"
        )
        try:
            validated = validate_remote_file_url(url)
            L(f"validated_len_eq={len(validated) == len(url)} validated_eq={validated == url}")
        except Exception as e:  # noqa: BLE001
            L(f"validate_failed={type(e).__name__}:{e}")
        L(
            f"pct_2525_in_query={'%2525' in parts.query} "
            f"pct_25_count={parts.query.count('%')}"
        )

        t0 = time.monotonic()
        with httpx.Client(timeout=60, follow_redirects=True) as http:
            resp = http.get(url)
            L(
                f"local_signed_GET status={resp.status_code} bytes={len(resp.content)} "
                f"elapsed_ms={int((time.monotonic() - t0) * 1000)}"
            )
            L(f"content_type={resp.headers.get('content-type')!r}")
            L(
                f"redirects={len(resp.history)} "
                f"redirect_statuses={[h.status_code for h in resp.history]}"
            )
            L(f"final_url_host={urlsplit(str(resp.url)).hostname}")
            L(f"final_url_query_preserved={bool(urlsplit(str(resp.url)).query)}")
            L(
                "body_sha_match="
                f"{hashlib.sha256(resp.content).digest() == hashlib.sha256(SYNTH_PDF).digest()}"
            )
            L(f"starts_pdf={resp.content.startswith(b'%PDF')}")

        unsigned = httpx.get(url.split("?", 1)[0], timeout=30)
        L(f"unsigned_GET_status={unsigned.status_code}")

        L("")
        L("## 4. OCR via OSS signed URL")
        t0 = time.monotonic()
        try:
            r = client.process(url)
            L(
                f"PASSED http={r.http_status} elapsed_ms={r.elapsed_ms} "
                f"wall={int((time.monotonic() - t0) * 1000)}"
            )
            signed_ok = True
            signed_ms = r.elapsed_ms
        except OcrError as e:
            wall = int((time.monotonic() - t0) * 1000)
            L(
                f"FAILED code={e.code} http={e.http_status} "
                f"elapsed_ms={e.elapsed_ms} wall_ms={wall}"
            )
            L(f"msg_snip={e.message[:220]}")
            signed_ms = e.elapsed_ms or wall
    finally:
        if temp is not None:
            try:
                storage.delete(temp.key)
                L("")
                L(f"OSS delete: PASSED key_hash={short_hash(temp.key)}")
            except Exception as e:  # noqa: BLE001
                L(f"OSS delete FAILED: {e}")

    L("")
    L("## Evidence summary (no root-cause claim beyond data)")
    L(f"public_ocr_ok={pub_ok} public_ms={pub_ms}")
    L(f"public_with_query_ocr_ok={q_ok} public_with_query_ms={q_ms}")
    L(f"signed_ocr_ok={signed_ok} signed_ms={signed_ms}")
    L("Notes:")
    L("- Client JSON POST uses httpx json=; roundtrip equality tests client-side encoding/truncation.")
    L("- HTTP 504 after ~60s is nginx gateway timeout; alone it does not prove download vs OCR-processing stage.")
    L("- If public+query PASSES but OSS signed FAILS, query-params-alone is insufficient as sole explanation.")
    L("- If public+query also FAILS similarly, query handling remains a plausible shared factor (needs server logs).")
    L("- Local signed GET success proves object/signing from this network; does not prove OCR worker egress to Aliyun.")
    L("- Distinguish: client read_timeout is 300s; observed ~60s 504 is upstream nginx, not our client timeout.")

    _write(lines)
    return 0 if signed_ok else 2


def _write(lines: list[str]) -> None:
    path = ROOT / "output" / "oss_ocr_final_probe.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
