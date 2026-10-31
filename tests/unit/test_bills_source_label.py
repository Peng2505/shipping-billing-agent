"""Existing-bill source tracking for demo labels."""

from __future__ import annotations

from pathlib import Path

from billing_agent.pipeline import BillingPipeline, UploadedFile
from billing_agent.config import load_settings
import synthetic_builders as sb


def test_uploaded_existing_bills_marked_uploaded(tmp_path):
    settings = load_settings()
    # Avoid LLM/OCR: skip_extraction
    pipe = BillingPipeline(settings)
    pdf = sb.pdf_bytes("Debit Note\nHANDLING 10 USD\n")
    bills = Path("data/samples/synthetic_exam/existing_bills_no_change.json").read_bytes()
    result = pipe.run(
        [UploadedFile(name="x.pdf", data=pdf)],
        existing_bills_bytes=bills,
        existing_bills_name="existing_bills_no_change.json",
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        enable_ocr_upload=False,
        skip_extraction=True,
    )
    assert result.bills_source == "uploaded"
    assert result.bills_source_name == "existing_bills_no_change.json"
    assert result.demo_mode is True  # file is _synthetic
    assert len(result.existing_bills) == 1
    assert result.existing_bills[0].amount in {"125.50", "125.5"}
