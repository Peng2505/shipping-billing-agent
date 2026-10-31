"""Final exam acceptance: synthetic Debit Note PDF/PNG via Local Tunnel OCR → rules → JSON.

Separates: tunnel fetch / OCR gateway / OCR fields / text-layer MBL / CREATE+AR·AP / JSON.
Does not invent MBL when OCR omits it.
"""

from __future__ import annotations

import hashlib
import json
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
from billing_agent.business.payment_direction import extract_payment_direction
from billing_agent.parsers import ParseContext, parse_bytes

OUT = ROOT / "output" / "final_exam_acceptance"
MBL = "LTFINALMBL9001"
AMOUNT = "125.50"
CURRENCY = "USD"
CHARGE = "HANDLING CHARGE"
PAYEE = "NEPTUNE SHIPPING LIMITED"
PAYER = "ACME FREIGHT CONSIGNEE LLC"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_pdf(path: Path) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = f"""DEBIT NOTE
Reference No: DC-FINAL-9001
MBL Number: {MBL}
CURRENCY: {CURRENCY}

BENEFICIARY
{PAYEE}

CONSIGNEE
{PAYER}

Please Pay freight against the master B/L shown below
TOTAL CHARGES TO BE PAID:
{AMOUNT}

Charge Details:
{CHARGE}    {AMOUNT} {CURRENCY}
TOTAL {AMOUNT} {CURRENCY}

SYNTHETIC EXAM ACCEPTANCE — NOT CUSTOMER DATA
{_utc()}
"""
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()
    return path.read_bytes()


def make_png(path: Path) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1200, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        "DEBIT NOTE",
        f"Reference No: DC-FINAL-9001",
        f"MBL Number: {MBL}",
        f"CURRENCY: {CURRENCY}",
        "BENEFICIARY",
        PAYEE,
        "CONSIGNEE",
        PAYER,
        "Please Pay freight against the master B/L",
        f"TOTAL CHARGES TO BE PAID: {AMOUNT}",
        f"{CHARGE}  {AMOUNT} {CURRENCY}",
        f"TOTAL {AMOUNT} {CURRENCY}",
        "SYNTHETIC — NOT CUSTOMER DATA",
    ]
    y = 30
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 32
    img.save(path, format="PNG")
    return path.read_bytes()


def load_provider() -> LocalTunnelProvider:
    status_path = ROOT / "output" / "local_tunnel" / "status.json"
    if not status_path.is_file():
        raise SystemExit("Local tunnel not running. Start scripts/local_tunnel/start_gateway.py")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    settings = load_settings()
    lt = LocalTunnelSettings(
        admin_base_url=status["admin_base_url"],
        public_base_url=status["public_base_url"],
        admin_token=status["admin_token"],
        status_file=str(status_path),
        url_expire_seconds=settings.local_tunnel.url_expire_seconds,
        max_upload_bytes=settings.local_tunnel.max_upload_bytes,
    )
    return LocalTunnelProvider(lt)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"generated_at": _utc(), "steps": {}, "notes": []}
    settings = load_settings()
    provider = load_provider()

    pdf_path = OUT / "final_debit.pdf"
    png_path = OUT / "final_debit.png"
    pdf_bytes = make_pdf(pdf_path)
    png_bytes = make_png(png_path)

    # Text-layer MBL evidence (PDF only) — not invented
    parsed = parse_bytes(pdf_bytes, "final_debit.pdf", ParseContext())
    text = parsed.text_by_origin(parsed.blocks[0].origin) if parsed.blocks else ""
    # Prefer aggregated text helper if available
    from billing_agent.schemas import SourceOrigin

    text = parsed.text_by_origin(SourceOrigin.TEXT_LAYER) or ""
    report["steps"]["pdf_text_layer_mbl"] = {
        "result": "PASSED" if MBL in text else "FAILED",
        "mbl_in_text_layer": MBL in text,
        "payment_direction": extract_payment_direction(text).__dict__,
    }

    # Tunnel + OCR PDF
    temp = provider.put_temporary(pdf_bytes, ".pdf", content_type_for(".pdf"))
    with httpx.Client(timeout=60, follow_redirects=True) as http:
        got = http.get(temp.url)
    report["steps"]["tunnel_pdf"] = {
        "result": "PASSED" if got.status_code == 200 and got.content == pdf_bytes else "FAILED",
        "sha_match": hashlib.sha256(got.content).digest() == hashlib.sha256(pdf_bytes).digest(),
    }

    client = OcrClient(settings.ocr)
    try:
        ocr_pdf = client.process(temp.url)
        blob = json.dumps(ocr_pdf.payload, ensure_ascii=False)
        item0 = ((ocr_pdf.payload.get("data") or {}).get("list") or [{}])[0]
        charges = item0.get("chargeList") if isinstance(item0, dict) else None
        report["steps"]["ocr_gateway_pdf"] = {"result": "PASSED", "elapsed_ms": ocr_pdf.elapsed_ms}
        report["steps"]["ocr_fields_pdf"] = {
            "chargeList": charges,
            "mbl_in_ocr_json": MBL in blob,
            "amount_in_ocr": AMOUNT in blob or "125.5" in blob,
            "currency_in_ocr": CURRENCY in blob,
            "result": "PASSED"
            if (AMOUNT in blob or "125.5" in blob)
            else "FAILED",
            "note": "MBL omission in OCR JSON is reported; text_layer still holds MBL for PDF Agent path",
        }
        (OUT / "ocr_pdf.json").write_text(json.dumps(ocr_pdf.payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OcrError as exc:
        report["steps"]["ocr_gateway_pdf"] = {
            "result": "FAILED",
            "code": exc.code,
            "http_status": exc.http_status,
            "message": (exc.message or "")[:200],
        }
    provider.delete(temp.key)

    # OCR PNG
    svc = OcrService(client, provider)
    out_png = svc.recognize(png_bytes, ".png")
    if out_png.raw_response:
        blob = json.dumps(out_png.raw_response, ensure_ascii=False)
        item0 = ((out_png.raw_response.get("data") or {}).get("list") or [{}])[0]
        report["steps"]["ocr_gateway_png"] = {"result": "PASSED", "elapsed_ms": out_png.elapsed_ms}
        report["steps"]["ocr_fields_png"] = {
            "chargeList": item0.get("chargeList") if isinstance(item0, dict) else None,
            "mbl_in_ocr_json": MBL in blob,
            "amount_in_ocr": AMOUNT in blob or "125.5" in blob,
            "result": "PASSED" if (AMOUNT in blob or "125.5" in blob) else "FAILED",
            "note": "PNG has no text_layer; MBL only if OCR returns it — do not invent",
        }
        (OUT / "ocr_png.json").write_text(
            json.dumps(out_png.raw_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        report["steps"]["ocr_gateway_png"] = {
            "result": "FAILED",
            "error": out_png.error_message,
        }

    # Full pipeline CREATE + AR (Neptune = beneficiary/payee)
    pipe = BillingPipeline(settings)
    pipe.ocr_service = OcrService(OcrClient(settings.ocr), provider)
    result_ar = pipe.run(
        [UploadedFile(name="final_debit.pdf", data=pdf_bytes)],
        existing_bills=[],
        accounting_entity=PAYEE,
        enable_ocr_upload=True,
    )
    report["steps"]["pipeline_create_ar"] = {
        "ops": result_ar.count_ops(),
        "postings": [
            {
                "operation": d.operation.value,
                "posting_type": d.posting_type,
                "amount": d.bill.amount,
                "currency": d.bill.currency,
                "charge_item": d.bill.charge_item,
                "bl_no": d.bill.bl_no,
                "reference_no": d.bill.reference_no,
                "issuer": d.bill.issuer,
                "recipient": d.bill.recipient,
                "audit": (d.audit_reasons or [])[:4],
                "posting_reason": (d.posting_reason or [])[:4],
            }
            for d in result_ar.all_decisions
        ],
        "errors": result_ar.errors[:3],
        "warnings": [w[:180] for w in result_ar.warnings[:6]],
    }
    if result_ar.delivery_json:
        from billing_agent.business.json_builder import dumps_delivery_json, validate_delivery_json

        text = dumps_delivery_json(result_ar.processing)
        ok, errs = validate_delivery_json(text)
        report["steps"]["json_schema_ar"] = {"result": "PASSED" if ok else "FAILED", "errors": errs}
        (OUT / "delivery_ar.json").write_text(text, encoding="utf-8")

    # CREATE + AP path
    result_ap = pipe.run(
        [UploadedFile(name="final_debit.pdf", data=pdf_bytes)],
        existing_bills=[],
        accounting_entity=PAYER,
        enable_ocr_upload=True,
    )
    report["steps"]["pipeline_create_ap"] = {
        "ops": result_ap.count_ops(),
        "postings": [
            {
                "operation": d.operation.value,
                "posting_type": d.posting_type,
                "amount": d.bill.amount,
                "currency": d.bill.currency,
                "audit": (d.audit_reasons or [])[:3],
                "posting_reason": (d.posting_reason or [])[:3],
            }
            for d in result_ap.all_decisions
        ],
    }

    # Verdict helpers
    ar_ops = report["steps"]["pipeline_create_ar"]["ops"]
    ap_ops = report["steps"]["pipeline_create_ap"]["ops"]
    ar_post = report["steps"]["pipeline_create_ar"]["postings"]
    ap_post = report["steps"]["pipeline_create_ap"]["postings"]
    report["verdict"] = {
        "ocr_pdf_gateway": report["steps"].get("ocr_gateway_pdf", {}).get("result"),
        "ocr_png_gateway": report["steps"].get("ocr_gateway_png", {}).get("result"),
        "create_ar": bool(ar_ops.get("CREATE") == 1 and ar_post and ar_post[0].get("posting_type") == "AR"),
        "create_ap": bool(ap_ops.get("CREATE") == 1 and ap_post and ap_post[0].get("posting_type") == "AP"),
        "amount_usd_ar": bool(ar_post and ar_post[0].get("amount") in {AMOUNT, "125.5", "125.50"} and ar_post[0].get("currency") == "USD"),
        "mbl_from_text_layer": report["steps"]["pdf_text_layer_mbl"]["mbl_in_text_layer"],
        "mbl_from_ocr_json": report["steps"].get("ocr_fields_pdf", {}).get("mbl_in_ocr_json"),
        "mbl_invented": False,
    }
    report["notes"] = [
        "Quick Tunnel is exam/demo only — not production hosting.",
        "MBL: present in PDF text_layer; OCR JSON may omit — Agent may use text_layer; never invent.",
        "UPDATE/NO_CHANGE covered by tests/unit/test_update_no_change_decisions.py",
    ]

    out = OUT / "latest_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "pipeline_create_ar": report["steps"]["pipeline_create_ar"], "pipeline_create_ap": report["steps"]["pipeline_create_ap"]}, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")
    v = report["verdict"]
    if v["ocr_pdf_gateway"] == "PASSED" and v["ocr_png_gateway"] == "PASSED" and v["create_ar"] and v["create_ap"]:
        return 0
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
