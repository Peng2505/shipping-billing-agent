"""Live security checks against deployed R2 Worker (no OCR calls).

Does not print secrets or full signed URLs.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from billing_agent.config import load_settings
from billing_agent.services.hmac_url import build_signed_get_url, encode_key_path
from billing_agent.services.r2_worker_storage import CloudflareR2WorkerProvider


def redact(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{parts.path}?exp=***&sig=***"


def main() -> int:
    settings = load_settings()
    report: dict = {"steps": {}}
    if not settings.r2_worker.configured:
        print(json.dumps({"error": "r2 not configured", "missing": settings.r2_worker.missing_fields()}))
        return 2

    base = settings.r2_worker.base_url.rstrip("/")
    provider = CloudflareR2WorkerProvider(settings.r2_worker)
    payload = b"%PDF-1.4\n% R2-SECURITY-PROBE\n"
    # Use provider put (authorized)
    temp = provider.put_temporary(payload, ".pdf", "application/pdf")
    key = temp.key
    report["steps"]["authorized_upload"] = {"result": "PASSED", "key_hash": hashlib.sha256(key.encode()).hexdigest()[:12]}

    with httpx.Client(timeout=60, follow_redirects=False) as http:
        # unauthorized upload
        r = http.put(
            f"{base}/admin/objects/{encode_key_path(key)}",
            content=b"evil",
            headers={"Content-Type": "application/pdf"},
        )
        report["steps"]["unauthorized_upload"] = {
            "result": "PASSED" if r.status_code in {401, 403} else "FAILED",
            "http_status": r.status_code,
        }

        # unauthorized delete
        r = http.delete(f"{base}/admin/objects/{encode_key_path(key)}")
        report["steps"]["unauthorized_delete"] = {
            "result": "PASSED" if r.status_code in {401, 403} else "FAILED",
            "http_status": r.status_code,
        }

        # bad signature
        bad = temp.url.rsplit("sig=", 1)[0] + "sig=" + ("11" * 32)
        r = http.get(bad)
        report["steps"]["bad_signature"] = {
            "result": "PASSED" if r.status_code in {401, 403} else "FAILED",
            "http_status": r.status_code,
            "url": redact(bad),
        }

        # expired
        expired = build_signed_get_url(
            base, key, secret=settings.r2_worker.hmac_secret, exp=int(time.time()) - 60
        )
        r = http.get(expired)
        report["steps"]["expired_signature"] = {
            "result": "PASSED" if r.status_code in {401, 403} else "FAILED",
            "http_status": r.status_code,
            "url": redact(expired),
        }

        # path traversal style GET (should 400)
        trav = f"{base}/o/ocr-tmp/../secret.pdf?exp=9999999999&sig={'00'*32}"
        r = http.get(trav)
        report["steps"]["path_traversal_get"] = {
            "result": "PASSED" if r.status_code in {400, 401, 403, 404} else "FAILED",
            "http_status": r.status_code,
        }

        # valid download + sha
        r = http.get(temp.url)
        sha_ok = r.status_code == 200 and hashlib.sha256(r.content).digest() == hashlib.sha256(payload).digest()
        report["steps"]["valid_signed_download"] = {
            "result": "PASSED" if sha_ok else "FAILED",
            "http_status": r.status_code,
            "sha_match": bool(sha_ok),
            "content_type": r.headers.get("content-type"),
            "redirect": r.is_redirect,
            "url": redact(temp.url),
        }

    # authorized delete then inaccessible
    provider.delete(key)
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        r = http.get(temp.url)
        report["steps"]["after_delete"] = {
            "result": "PASSED" if r.status_code in {401, 403, 404} else "FAILED",
            "http_status": r.status_code,
        }

    out = ROOT / "output" / "r2_worker_acceptance" / "security_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [k for k, v in report["steps"].items() if v.get("result") != "PASSED"]
    return 0 if not failed else 3


if __name__ == "__main__":
    raise SystemExit(main())
