"""R2 + Worker + OCR acceptance (synthetic shipping fee docs only).

Requires deployed Worker + .env:
  FILE_URL_PROVIDER=cloudflare_r2_worker
  R2_WORKER_BASE_URL=https://...
  R2_WORKER_UPLOAD_TOKEN=...
  R2_WORKER_HMAC_SECRET=...

Does NOT upload recruiter/customer files.
Field-level OCR assertions — success=true alone is not enough.

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\r2_worker_acceptance.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from billing_agent.config import load_settings
from billing_agent.services.file_url_factory import create_file_url_provider
from billing_agent.services.hmac_url import build_signed_get_url
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.ocr_service import OcrService, content_type_for

OUT = ROOT / "output" / "r2_worker_acceptance"
MBL_ANCHOR = "R2TESTMBL9911"
CHARGE_NAME = "HANDLING CHARGE"
AMOUNT_ANCHOR = "50.00"
CURRENCY_ANCHOR = "USD"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_fee_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        "DEBIT NOTE\n"
        f"MBL: {MBL_ANCHOR}\n"
        f"CURRENCY: {CURRENCY_ANCHOR}\n"
        f"{CHARGE_NAME}    {AMOUNT_ANCHOR}\n"
        f"TOTAL {AMOUNT_ANCHOR}\n"
        "SYNTHETIC — NOT CUSTOMER DATA\n"
        f"Generated: {_utc()}\n"
    )
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()


def make_fee_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1000, 500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        "DEBIT NOTE / INVOICE",
        f"MBL: {MBL_ANCHOR}",
        f"CURRENCY: {CURRENCY_ANCHOR}",
        f"{CHARGE_NAME}  {AMOUNT_ANCHOR}",
        f"TOTAL {AMOUNT_ANCHOR}",
        "SYNTHETIC — NOT CUSTOMER DATA",
        _utc(),
    ]
    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 36
    img.save(path, format="PNG")


def payload_blob(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def field_assertions(payload: dict, *, kind: str) -> list[str]:
    """Return list of failure reasons; empty means field-level pass."""
    errors: list[str] = []
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return ["success!=true"]
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list) or not data["list"]:
        return ["missing data.list"]
    blob = payload_blob(payload)
    # Unique anchors from the synthetic document
    if MBL_ANCHOR not in blob and AMOUNT_ANCHOR not in blob and "50" not in blob:
        errors.append(f"{kind}: neither MBL nor amount anchors found in OCR JSON")
    # Prefer structured chargeList when present
    item0 = data["list"][0] if isinstance(data["list"][0], dict) else {}
    charges = item0.get("chargeList") if isinstance(item0, dict) else None
    mbl = ""
    if isinstance(item0, dict):
        mbl = str(item0.get("mblNumber") or item0.get("mbl") or "")
    if MBL_ANCHOR in blob or MBL_ANCHOR in mbl:
        pass
    elif isinstance(charges, list) and any(
        AMOUNT_ANCHOR in json.dumps(c, ensure_ascii=False)
        or re.search(r"\b50(\.0+)?\b", json.dumps(c, ensure_ascii=False))
        for c in charges
        if isinstance(c, dict)
    ):
        pass
    elif AMOUNT_ANCHOR in blob or re.search(r"\b50(\.00)?\b", blob):
        pass
    else:
        errors.append(f"{kind}: structured fields lack MBL/amount evidence")
    return errors


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    report: dict = {
        "generated_at": _utc(),
        "provider_setting": settings.file_url_provider or "(auto)",
        "steps": {},
        "notes": [],
    }

    provider = create_file_url_provider(settings)
    if provider is None or provider.name != "cloudflare_r2_worker":
        report["steps"]["config"] = {
            "result": "BLOCKED",
            "active": getattr(provider, "name", None),
            "r2_missing": settings.r2_worker.missing_fields(),
            "hint": "Set FILE_URL_PROVIDER=cloudflare_r2_worker and R2_WORKER_* secrets after deploy.",
        }
        _write(report)
        print(json.dumps(report["steps"]["config"], ensure_ascii=False, indent=2))
        return 2

    report["active_provider"] = provider.name
    pdf_path = OUT / "synth_fee.pdf"
    png_path = OUT / "synth_fee.png"
    make_fee_pdf(pdf_path)
    make_fee_png(png_path)

    # --- upload + SHA + signed GET ---
    pdf_bytes = pdf_path.read_bytes()
    temp = provider.put_temporary(pdf_bytes, ".pdf", content_type_for(".pdf"))
    report["steps"]["upload_pdf"] = {
        "result": "PASSED",
        "key_suffix": temp.key.split("/")[-1],
        "bytes": len(pdf_bytes),
    }

    with httpx.Client(timeout=60, follow_redirects=False) as http:
        t0 = time.monotonic()
        got = http.get(temp.url)
        report["steps"]["worker_get_pdf"] = {
            "result": "PASSED" if got.status_code == 200 else "FAILED",
            "http_status": got.status_code,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "redirect": got.is_redirect,
            "content_type": got.headers.get("content-type"),
            "sha_match": hashlib.sha256(got.content).digest() == hashlib.sha256(pdf_bytes).digest(),
        }
        if got.status_code != 200 or not report["steps"]["worker_get_pdf"]["sha_match"]:
            provider.delete(temp.key)
            _write(report)
            return 3

        # expired token
        expired_url = build_signed_get_url(
            settings.r2_worker.base_url,
            temp.key,
            secret=settings.r2_worker.hmac_secret,
            exp=int(time.time()) - 30,
        )
        exp_resp = http.get(expired_url)
        report["steps"]["expired_token"] = {
            "result": "PASSED" if exp_resp.status_code in {401, 403} else "FAILED",
            "http_status": exp_resp.status_code,
        }

        # bad signature
        bad_url = temp.url.rsplit("sig=", 1)[0] + "sig=" + ("ab" * 32)
        bad_resp = http.get(bad_url)
        report["steps"]["bad_signature"] = {
            "result": "PASSED" if bad_resp.status_code in {401, 403} else "FAILED",
            "http_status": bad_resp.status_code,
        }

        # unauthorized upload
        unauth = http.put(
            f"{settings.r2_worker.base_url.rstrip('/')}/admin/objects/{temp.key}",
            content=b"nope",
            headers={"Content-Type": "application/pdf"},
        )
        report["steps"]["unauthorized_upload"] = {
            "result": "PASSED" if unauth.status_code in {401, 403} else "FAILED",
            "http_status": unauth.status_code,
        }

    # --- OCR PDF (one call) ---
    client = OcrClient(settings.ocr)
    t0 = time.monotonic()
    try:
        ocr_pdf = client.process(temp.url)
        fails = field_assertions(ocr_pdf.payload, kind="pdf")
        report["steps"]["ocr_pdf"] = {
            "result": "PASSED" if not fails else "FAILED_FIELDS",
            "http_status": ocr_pdf.http_status,
            "elapsed_ms": ocr_pdf.elapsed_ms,
            "wall_ms": int((time.monotonic() - t0) * 1000),
            "field_errors": fails,
            "payload_sha12": hashlib.sha256(payload_blob(ocr_pdf.payload).encode()).hexdigest()[:12],
        }
        (OUT / "ocr_pdf_response.json").write_text(
            json.dumps(ocr_pdf.payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OcrError as exc:
        report["steps"]["ocr_pdf"] = {
            "result": "FAILED",
            "code": exc.code,
            "http_status": exc.http_status,
            "elapsed_ms": exc.elapsed_ms,
            "message": (exc.message or "")[:240],
        }

    provider.delete(temp.key)
    with httpx.Client(timeout=30) as http:
        after = http.get(temp.url)
    report["steps"]["delete_pdf"] = {
        "result": "PASSED" if after.status_code in {401, 403, 404} else "FAILED",
        "http_status": after.status_code,
        "note": "signed URL may still verify HMAC but object missing → 404",
    }

    # --- PNG via OcrService (upload→OCR→delete) ---
    service = OcrService.from_settings(settings)
    png_bytes = png_path.read_bytes()
    outcome = service.recognize(png_bytes, ".png")
    png_step: dict = {
        "ocr_status": outcome.status.value if outcome.status else None,
        "http_status": outcome.http_status,
        "elapsed_ms": outcome.elapsed_ms,
        "error_code": outcome.error_code,
        "storage_provider": outcome.storage_provider,
    }
    if outcome.raw_response:
        fails = field_assertions(outcome.raw_response, kind="png")
        png_step["field_errors"] = fails
        png_step["result"] = "PASSED" if not fails else "FAILED_FIELDS"
        (OUT / "ocr_png_response.json").write_text(
            json.dumps(outcome.raw_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        png_step["result"] = "FAILED"
        png_step["error_message"] = (outcome.error_message or "")[:240]
    report["steps"]["ocr_png_via_service"] = png_step

    report["notes"].append(
        "Field-level pass requires MBL R2TESTMBL9911 and/or amount 50(.00) evidence in OCR JSON; "
        "HTTP 200 + success=true alone is insufficient."
    )
    _write(report)
    print(json.dumps(report["steps"], ensure_ascii=False, indent=2))

    hard = [
        report["steps"].get("worker_get_pdf", {}).get("result"),
        report["steps"].get("expired_token", {}).get("result"),
        report["steps"].get("bad_signature", {}).get("result"),
        report["steps"].get("unauthorized_upload", {}).get("result"),
    ]
    ocr_ok = report["steps"].get("ocr_pdf", {}).get("result") == "PASSED"
    png_ok = report["steps"].get("ocr_png_via_service", {}).get("result") == "PASSED"
    if all(x == "PASSED" for x in hard) and ocr_ok and png_ok:
        return 0
    if all(x == "PASSED" for x in hard) and (
        report["steps"].get("ocr_pdf", {}).get("result") in {"PASSED", "FAILED_FIELDS"}
    ):
        # Storage path OK; OCR field extraction may need richer synth layout.
        return 4
    return 5


def _write(report: dict) -> None:
    path = OUT / "latest_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
