"""Local Tunnel → OCR → optional Agent/rules acceptance (synthetic shipping bills).

Requires:
  1) scripts/local_tunnel/start_gateway.py running
  2) FILE_URL_PROVIDER=local_tunnel + LOCAL_TUNNEL_ADMIN_TOKEN in .env
     (or copy values from output/local_tunnel/env.snippet)

Reports separately: fetch / OCR gateway / field extraction / business pipeline.
Does NOT upload customer files.
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

from billing_agent.config import LocalTunnelSettings, load_settings
from billing_agent.pipeline import BillingPipeline, UploadedFile
from billing_agent.services.local_tunnel_storage import LocalTunnelProvider
from billing_agent.services.ocr_client import OcrClient, OcrError
from billing_agent.services.ocr_service import OcrService, content_type_for

OUT = ROOT / "output" / "local_tunnel_acceptance"
MBL = "LTTESTMBL7788"
AMOUNT = "125.50"
CURRENCY = "USD"
CHARGE = "HANDLING CHARGE"
PAYEE = "NEPTUNE SHIPPING LIMITED"
PAYER = "ACME FREIGHT CONSIGNEE LLC"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        "DEBIT NOTE\n"
        f"MBL: {MBL}\n"
        f"BENEFICIARY: {PAYEE}\n"
        f"BILL TO / CONSIGNEE: {PAYER}\n"
        f"CURRENCY: {CURRENCY}\n"
        f"{CHARGE}    {AMOUNT}\n"
        f"TOTAL {AMOUNT}\n"
        "SYNTHETIC — NOT CUSTOMER DATA\n"
        f"{_utc()}\n"
    )
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()


def make_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1100, 560), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        "DEBIT NOTE / INVOICE",
        f"MBL: {MBL}",
        f"BENEFICIARY: {PAYEE}",
        f"BILL TO: {PAYER}",
        f"CURRENCY: {CURRENCY}",
        f"{CHARGE}  {AMOUNT}",
        f"TOTAL {AMOUNT}",
        "SYNTHETIC — NOT CUSTOMER DATA",
        _utc(),
    ]
    y = 36
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 34
    img.save(path, format="PNG")


def field_check(payload: dict, kind: str) -> dict:
    blob = json.dumps(payload, ensure_ascii=False)
    ok_success = payload.get("success") is True
    items = (payload.get("data") or {}).get("list") if isinstance(payload.get("data"), dict) else None
    has_list = isinstance(items, list) and len(items) > 0
    anchors = {
        "mbl": MBL in blob,
        "amount": AMOUNT in blob or bool(re.search(r"\b125([.,]50)?\b", blob)),
        "currency": CURRENCY in blob or "usd" in blob.lower(),
        "charge_name": "HANDLING" in blob.upper() or "CHARGE" in blob.upper(),
    }
    return {
        "kind": kind,
        "ocr_http_success_flag": ok_success,
        "has_data_list": has_list,
        "anchors": anchors,
        "field_level_pass": ok_success and has_list and (anchors["mbl"] or anchors["amount"]),
        "payload_sha12": hashlib.sha256(blob.encode()).hexdigest()[:12],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    status_path = ROOT / "output" / "local_tunnel" / "status.json"
    report: dict = {
        "generated_at": _utc(),
        "file_url_provider": settings.file_url_provider or "(from status)",
        "steps": {},
        "notes": [],
    }

    if not status_path.is_file():
        report["steps"]["config"] = {
            "result": "BLOCKED",
            "hint": "Start scripts/local_tunnel/start_gateway.py first (status.json missing)",
        }
        _write(report)
        print(json.dumps(report["steps"], ensure_ascii=False, indent=2))
        return 2

    status = json.loads(status_path.read_text(encoding="utf-8"))
    lt = LocalTunnelSettings(
        admin_base_url=str(status.get("admin_base_url") or "http://127.0.0.1:8765"),
        public_base_url=str(status.get("public_base_url") or ""),
        admin_token=str(status.get("admin_token") or ""),
        status_file=str(status_path),
        url_expire_seconds=settings.local_tunnel.url_expire_seconds,
        max_upload_bytes=settings.local_tunnel.max_upload_bytes,
    )
    if not lt.configured or not lt.public_base_url.startswith("https://"):
        report["steps"]["config"] = {"result": "BLOCKED", "hint": "status.json incomplete"}
        _write(report)
        return 2
    provider = LocalTunnelProvider(lt)

    pdf_path = OUT / "synth_debit.pdf"
    png_path = OUT / "synth_debit.png"
    make_pdf(pdf_path)
    make_png(png_path)

    # --- PDF fetch layer ---
    pdf_bytes = pdf_path.read_bytes()
    try:
        temp = provider.put_temporary(pdf_bytes, ".pdf", content_type_for(".pdf"))
    except Exception as exc:
        report["steps"]["upload_pdf"] = {"result": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
        _write(report)
        return 3
    report["steps"]["upload_pdf"] = {"result": "PASSED", "key_hash": hashlib.sha256(temp.key.encode()).hexdigest()[:12]}

    with httpx.Client(timeout=60, follow_redirects=True) as http:
        r = http.get(temp.url)
        report["steps"]["tunnel_fetch_pdf"] = {
            "result": "PASSED" if r.status_code == 200 and r.content == pdf_bytes else "FAILED",
            "http_status": r.status_code,
            "sha_match": hashlib.sha256(r.content).digest() == hashlib.sha256(pdf_bytes).digest(),
        }
        # bad token
        parts = temp.url.split("/")
        parts[-2] = "invalid-token-xxx"
        bad = "/".join(parts)
        br = http.get(bad)
        report["steps"]["bad_token"] = {
            "result": "PASSED" if br.status_code in {401, 403, 404} else "FAILED",
            "http_status": br.status_code,
        }

    # --- OCR PDF ---
    client = OcrClient(settings.ocr)
    t0 = time.monotonic()
    try:
        ocr = client.process(temp.url)
        fc = field_check(ocr.payload, "pdf")
        report["steps"]["ocr_gateway_pdf"] = {
            "result": "PASSED",
            "elapsed_ms": ocr.elapsed_ms,
            "wall_ms": int((time.monotonic() - t0) * 1000),
        }
        report["steps"]["ocr_fields_pdf"] = {
            "result": "PASSED" if fc["field_level_pass"] else "PARTIAL_OR_FAILED",
            **fc,
        }
        (OUT / "ocr_pdf.json").write_text(json.dumps(ocr.payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OcrError as exc:
        report["steps"]["ocr_gateway_pdf"] = {
            "result": "FAILED",
            "code": exc.code,
            "http_status": exc.http_status,
            "elapsed_ms": exc.elapsed_ms,
            "message": (exc.message or "")[:200],
        }
        report["steps"]["ocr_fields_pdf"] = {"result": "SKIPPED"}

    provider.delete(temp.key)

    # --- PNG via OcrService ---
    service = OcrService(client, provider)
    outcome = service.recognize(png_path.read_bytes(), ".png")
    png_step = {
        "ocr_status": outcome.status.value if outcome.status else None,
        "storage_provider": outcome.storage_provider,
        "http_status": outcome.http_status,
        "elapsed_ms": outcome.elapsed_ms,
        "error_code": outcome.error_code,
    }
    if outcome.raw_response:
        fc = field_check(outcome.raw_response, "png")
        png_step["ocr_gateway"] = "PASSED"
        png_step["ocr_fields"] = fc
        png_step["result"] = "PASSED" if fc["field_level_pass"] else "PARTIAL_OR_FAILED"
        (OUT / "ocr_png.json").write_text(
            json.dumps(outcome.raw_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        png_step["ocr_gateway"] = "FAILED"
        png_step["result"] = "FAILED"
        png_step["error_message"] = (outcome.error_message or "")[:200]
    report["steps"]["ocr_png"] = png_step

    # --- Business pipeline (PDF bytes as upload; uses OCR if enable flag) ---
    if settings.llm.configured:
        pipe = BillingPipeline(settings)
        # Ensure pipeline uses same provider
        pipe.ocr_service = OcrService(OcrClient(settings.ocr), provider)
        result = pipe.run(
            [UploadedFile(name="synth_debit.pdf", data=pdf_bytes)],
            existing_bills=[],
            accounting_entity=PAYER,
            enable_ocr_upload=True,
        )
        report["steps"]["pipeline"] = {
            "result": "RAN",
            "ops": result.count_ops(),
            "decisions": len(result.all_decisions),
            "delivery_records": len(result.delivery_json),
            "errors": result.errors[:5],
            "warnings": [w[:160] for w in result.warnings[:6]],
            "postings": [
                {
                    "operation": d.operation.value,
                    "posting_type": d.posting_type,
                    "amount": d.bill.amount,
                    "currency": d.bill.currency,
                    "charge_item": d.bill.charge_item,
                }
                for d in result.all_decisions[:5]
            ],
        }
        if result.delivery_json:
            from billing_agent.business.json_builder import dumps_delivery_json, validate_delivery_json

            text = dumps_delivery_json(result.processing)
            ok, errs = validate_delivery_json(text)
            report["steps"]["json_schema"] = {"result": "PASSED" if ok else "FAILED", "errors": errs}
            (OUT / "delivery.json").write_text(text, encoding="utf-8")
    else:
        report["steps"]["pipeline"] = {"result": "SKIPPED", "reason": "LLM not configured"}

    report["notes"].extend(
        [
            "Separate layers: tunnel_fetch / ocr_gateway / ocr_fields / pipeline must not be collapsed into one PASSED.",
            "Quick Tunnel is for exam/demo only; URL rotates each start_gateway run.",
        ]
    )
    _write(report)
    print(json.dumps(report["steps"], ensure_ascii=False, indent=2))

    fetch_ok = report["steps"].get("tunnel_fetch_pdf", {}).get("result") == "PASSED"
    ocr_pdf = report["steps"].get("ocr_gateway_pdf", {}).get("result") == "PASSED"
    ocr_png = report["steps"].get("ocr_png", {}).get("ocr_gateway") == "PASSED"
    if fetch_ok and ocr_pdf and ocr_png:
        return 0
    if fetch_ok and (ocr_pdf or ocr_png):
        return 4
    return 5


def _write(report: dict) -> None:
    path = OUT / "latest_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
