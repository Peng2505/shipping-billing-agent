"""Real Pipeline acceptance for CREATE / NO_CHANGE / PENDING / UPDATE (rules path).

Uses synthetic exam PDF. OCR upload OFF by default (saves OCR quota; text_layer sufficient).
UPDATE is verified via decision_engine + ChangeRequest (same path as Agent-emitted changes).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from billing_agent.business.bill_store import load_bills_path
from billing_agent.business.decision_engine import decide_for_document
from billing_agent.business.json_builder import dumps_delivery_json, validate_delivery_json
from billing_agent.config import load_settings
from billing_agent.pipeline import BillingPipeline, UploadedFile
from billing_agent.schemas import (
    ChangeRequest,
    ChargeNature,
    EvidenceRef,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    OperationType,
)

SAMPLES = ROOT / "data" / "samples" / "synthetic_exam"
OUT = ROOT / "output" / "demo_decision_acceptance"
PAYEE = "NEPTUNE SHIPPING LIMITED"
PAYER = "ACME FREIGHT CONSIGNEE LLC"


def _ops(result) -> dict:
    return result.count_ops()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = (SAMPLES / "exam_debit_create.pdf").read_bytes()
    settings = load_settings()
    pipe = BillingPipeline(settings)
    report: dict = {"steps": {}}

    # CREATE + AR
    r_ar = pipe.run(
        [UploadedFile(name="exam_debit_create.pdf", data=pdf)],
        existing_bills=[],
        accounting_entity=PAYEE,
        enable_ocr_upload=False,
    )
    report["steps"]["create_ar"] = {
        "ops": _ops(r_ar),
        "posting": [
            {"op": d.operation.value, "posting_type": d.posting_type, "amount": d.bill.amount}
            for d in r_ar.all_decisions
        ],
        "json_ok": validate_delivery_json(dumps_delivery_json(r_ar.processing))[0]
        if r_ar.delivery_json
        else False,
    }

    # CREATE + AP
    r_ap = pipe.run(
        [UploadedFile(name="exam_debit_create.pdf", data=pdf)],
        existing_bills=[],
        accounting_entity=PAYER,
        enable_ocr_upload=False,
    )
    report["steps"]["create_ap"] = {
        "ops": _ops(r_ap),
        "posting": [
            {"op": d.operation.value, "posting_type": d.posting_type}
            for d in r_ap.all_decisions
        ],
    }

    # NO_CHANGE — existing equals incoming
    bills_nc = load_bills_path(SAMPLES / "existing_bills_no_change.json")
    r_nc = pipe.run(
        [UploadedFile(name="exam_debit_create.pdf", data=pdf)],
        existing_bills=bills_nc,
        accounting_entity=PAYEE,
        enable_ocr_upload=False,
    )
    report["steps"]["no_change"] = {
        "ops": _ops(r_nc),
        "posting": [
            {
                "op": d.operation.value,
                "match": d.match.level.value if d.match else None,
                "amount": d.bill.amount,
            }
            for d in r_nc.all_decisions
        ],
    }

    # PENDING — amount differs, no change evidence
    bills_up = load_bills_path(SAMPLES / "existing_bills_update.json")
    r_pending = pipe.run(
        [UploadedFile(name="exam_debit_create.pdf", data=pdf)],
        existing_bills=bills_up,
        accounting_entity=PAYEE,
        enable_ocr_upload=False,
    )
    report["steps"]["pending_amount_diff"] = {
        "ops": _ops(r_pending),
        "posting": [
            {"op": d.operation.value, "audit": (d.audit_reasons or [])[:2]}
            for d in r_pending.all_decisions
        ],
    }

    # UPDATE — same matching path with explicit ChangeRequest (Agent grounding path)
    grounded = GroundedExtraction(
        result=ExtractionResult(
            document_type=EvidencedValue(value="Debit Note"),
            issuer=EvidencedValue(value=PAYEE),
            recipient=EvidencedValue(value=PAYER),
            reference_no=EvidencedValue(value="DC-FINAL-9001"),
        ),
        actual_charges=[
            ExtractedCharge(
                raw_name="HANDLING CHARGE",
                nature=ChargeNature.ACTUAL,
                amount="125.50",
                currency="USD",
                evidence=[EvidenceRef(block_id="b1", quote="HANDLING CHARGE 125.50 USD")],
            )
        ],
    )
    decisions = decide_for_document(
        grounded,
        bills_up,
        accounting_entity=PAYEE,
        file_sha256="exam-update",
        change_requests=[
            ChangeRequest(
                field="amount",
                new_value="125.50",
                evidence=[EvidenceRef(block_id="b1", quote="amend amount to 125.50")],
            )
        ],
    )
    report["steps"]["update_with_change_request"] = {
        "operation": decisions[0].operation.value if decisions else None,
        "amount": decisions[0].bill.amount if decisions else None,
        "changes": [c.field for c in (decisions[0].changes or [])] if decisions else [],
    }

    # Verdict
    s = report["steps"]
    report["verdict"] = {
        "create_ar": s["create_ar"]["ops"].get("CREATE") == 1
        and s["create_ar"]["posting"]
        and s["create_ar"]["posting"][0].get("posting_type") == "AR",
        "create_ap": s["create_ap"]["ops"].get("CREATE") == 1
        and s["create_ap"]["posting"]
        and s["create_ap"]["posting"][0].get("posting_type") == "AP",
        "no_change": s["no_change"]["ops"].get("NO_CHANGE") == 1,
        "pending": s["pending_amount_diff"]["ops"].get("PENDING_REVIEW") == 1,
        "update": s["update_with_change_request"].get("operation") == OperationType.UPDATE.value,
        "json_ok": bool(s["create_ar"].get("json_ok")),
        "ocr_used": False,
        "note": "Pipeline text_layer path; UPDATE via ChangeRequest (same engine as Agent).",
    }
    out = OUT / "latest_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["verdict"], ensure_ascii=False, indent=2))
    print(f"Wrote {out}")
    v = report["verdict"]
    return 0 if all(v[k] for k in ("create_ar", "create_ap", "no_change", "pending", "update", "json_ok")) else 4


if __name__ == "__main__":
    raise SystemExit(main())
