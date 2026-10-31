"""Phase 5 sample acceptance runner (real pipeline, no invented OCR success).

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\phase5_sample_acceptance.py

Writes:
  output/phase5_sample_acceptance.json
  output/sample_*.json  (delivery JSON per sample when available)

Does NOT enable OCR upload unless AUTHORIZE_OCR_UPLOAD=1 and enable flag is set.
Default: OCR upload disabled; PDF text_layer may still be used and labelled honestly.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from billing_agent.business.json_builder import dumps_delivery_json, validate_delivery_json
from billing_agent.config import load_settings
from billing_agent.pipeline import BillingPipeline, UploadedFile, load_default_synthetic_bills
from billing_agent.schemas import SourceOrigin

SAMPLES = ROOT / "data" / "samples"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)


def _find(pattern: str) -> Path:
    matches = sorted(SAMPLES.glob(pattern))
    if len(matches) != 1:
        raise FileNotFoundError(f"{pattern}: {matches}")
    return matches[0]


def _charge_summary(result) -> list[dict]:
    rows = []
    for d in result.all_decisions:
        rows.append(
            {
                "operation": d.operation.value,
                "posting_type": d.posting_type,
                "charge_item": d.bill.charge_item,
                "amount": d.bill.amount,
                "currency": d.bill.currency,
                "reference_no": d.bill.reference_no,
                "match": d.match.level.value if d.match else None,
                "changed_fields": [c.field for c in (d.changes or [])],
            }
        )
    return rows


def _origins(result) -> dict:
    counts = {"native": 0, "text_layer": 0, "ocr_api": 0}
    ocr_statuses = []
    for o in result.outcomes:
        for b in o.document.blocks:
            key = b.origin.value
            if key in counts:
                counts[key] += 1
        if o.document.ocr is not None:
            ocr_statuses.append(
                {
                    "file": o.document.file_name,
                    "status": o.document.ocr.status.value,
                    "http_status": o.document.ocr.http_status,
                    "error_code": o.document.ocr.error_code,
                }
            )
    return {"block_origins": counts, "ocr_records": ocr_statuses}


def run_one(name: str, path: Path, accounting_entity: str | None, enable_ocr: bool) -> dict:
    settings = load_settings()
    files = [UploadedFile(name=path.name, data=path.read_bytes())]
    existing = load_default_synthetic_bills()
    stages: list[dict] = []

    def on_stage(stage: str, status: str, event: dict) -> None:
        stages.append(event)

    pipeline = BillingPipeline(settings, on_stage=on_stage)
    result = pipeline.run(
        files,
        existing_bills=existing,
        accounting_entity=accounting_entity,
        enable_ocr_upload=enable_ocr,
    )

    delivery_ok = False
    delivery_errors: list[str] = []
    if result.delivery_json:
        text = dumps_delivery_json(result.processing)
        delivery_ok, delivery_errors = validate_delivery_json(text)
        (OUT / f"sample_{name}_result.json").write_text(text, encoding="utf-8")

    return {
        "sample": name,
        "file": path.name,
        "accounting_entity": accounting_entity,
        "enable_ocr_upload": enable_ocr,
        "demo_mode_synthetic_bills": True,
        "llm_configured": bool(settings.llm.configured),
        "elapsed_ms": result.elapsed_ms,
        "ops": result.count_ops(),
        "charges": _charge_summary(result),
        "origins": _origins(result),
        "errors": result.errors,
        "warnings": [w[:240] for w in result.warnings],
        "delivery_records": len(result.delivery_json),
        "delivery_valid": delivery_ok,
        "delivery_errors": delivery_errors,
        "tool_traces": [
            {
                "file": o.document.file_name,
                "tools": len(o.grounded.tool_trace) if o.grounded else 0,
                "extract_error": o.extract_error,
                "actual_charges": len(o.grounded.actual_charges) if o.grounded else 0,
                "excluded_charges": len(o.grounded.excluded_charges) if o.grounded else 0,
            }
            for o in result.outcomes
        ],
        "stage_count": len(stages),
        "text_layer_blocks": _origins(result)["block_origins"].get("text_layer", 0),
        "ocr_api_blocks": _origins(result)["block_origins"].get("ocr_api", 0),
        "honesty_note": (
            "OCR_API blocks only count when OCR gateway actually returned data. "
            "PDF text_layer must not be labelled as OCR success."
        ),
    }


def main() -> int:
    enable_ocr = False  # keep closed for recruiter samples unless explicitly authorized
    cases = [
        ("eml", _find("*PRE-ALERT*.eml"), "NEPTUNE SHIPPING LIMITED"),
        ("pdf1", SAMPLES / "PDF示例账单1.pdf", "NEPTUNE SHIPPING LIMITED"),
        ("pdf2", SAMPLES / "PDF 示例账单2.pdf", "NEPTUNE SHIPPING LIMITED"),
        ("png", SAMPLES / "图片示例.png", "NEPTUNE SHIPPING LIMITED"),
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ocr_upload_enabled": enable_ocr,
        "cases": [],
    }
    for name, path, entity in cases:
        print(f"=== running {name}: {path.name} ===", flush=True)
        try:
            case = run_one(name, path, entity, enable_ocr)
        except Exception as exc:
            case = {
                "sample": name,
                "file": path.name,
                "status": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
            }
        report["cases"].append(case)
        print(json.dumps({k: case.get(k) for k in ("sample", "ops", "delivery_records", "errors")}, ensure_ascii=False), flush=True)

    out_path = OUT / "phase5_sample_acceptance.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
