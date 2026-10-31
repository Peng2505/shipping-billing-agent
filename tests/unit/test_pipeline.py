"""Pipeline orchestration unit tests (no real LLM/OCR)."""

from __future__ import annotations

from billing_agent.pipeline import BillingPipeline, UploadedFile, service_status
from billing_agent.schemas import (
    ChargeNature,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    OcrStatus,
)
from billing_agent.services.ocr_service import OcrService
from billing_agent.config import load_settings
import synthetic_builders as sb


class _FakeAgent:
    configured = True

    def extract(self, document):
        return GroundedExtraction(
            result=ExtractionResult(
                document_type=EvidencedValue(value="Debit Note", evidence=[]),
                reference_no=EvidencedValue(value="SYN-PIPE-1", evidence=[]),
                issuer=EvidencedValue(value="NEPTUNE SHIPPING LIMITED", evidence=[]),
                charges=[
                    ExtractedCharge(
                        raw_name="Handling Charge",
                        nature=ChargeNature.ACTUAL,
                        amount="40.00",
                        currency="USD",
                    )
                ],
            ),
            actual_charges=[
                ExtractedCharge(
                    raw_name="Handling Charge",
                    nature=ChargeNature.ACTUAL,
                    amount="40.00",
                    currency="USD",
                )
            ],
            model_name="fake",
            structured_strategy="fake",
            elapsed_ms=1,
        )


def test_service_status_no_secrets():
    status = service_status(load_settings())
    blob = str(status)
    assert "sk-" not in blob
    assert "AccessKey" not in blob
    assert "llm_configured" in status
    assert "oss_configured" in status


def test_pipeline_parse_and_decide_with_fake_agent():
    settings = load_settings()
    # Force OCR unconfigured path (no upload)
    ocr = OcrService(client=None, url_provider=None) if False else OcrService.from_settings(settings)
    # Replace with unconfigured provider to avoid real OCR in unit test
    from billing_agent.services.ocr_client import OcrClient

    ocr = OcrService(OcrClient(settings.ocr), url_provider=None)

    stages = []
    pipeline = BillingPipeline(
        settings,
        ocr_service=ocr,
        extraction_agent=_FakeAgent(),  # type: ignore[arg-type]
        on_stage=lambda s, st, ev: stages.append(ev),
    )
    pdf = sb.pdf_bytes(
        "SYNTHETIC TEST DATA\nDebit Note SYN-PIPE-1\n"
        "NEPTUNE SHIPPING LIMITED\nHandling Charge USD 40.00\nTotal USD 40.00"
    )
    result = pipeline.run(
        [UploadedFile(name="synthetic_pipe.pdf", data=pdf)],
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        existing_bills=[],
    )
    assert result.outcomes
    assert result.outcomes[0].document.ocr is None or result.outcomes[0].document.ocr.status in {
        OcrStatus.NOT_CONFIGURED,
        OcrStatus.FAILED,
        OcrStatus.SUCCESS,
        OcrStatus.NOT_APPLICABLE,
    }
    # Default enable_ocr_upload=False → intentional NOT_APPLICABLE (not storage misconfig).
    ocr_out = result.outcomes[0].document.ocr
    if ocr_out is not None:
        assert ocr_out.status == OcrStatus.NOT_APPLICABLE
        assert ocr_out.error_code == "OCR_NOT_AUTHORIZED"
    assert result.outcomes[0].grounded is not None
    assert result.delivery_json
    assert result.delivery_json[0]["operation"] in {"CREATE", "PENDING_REVIEW", "UPDATE", "NO_CHANGE"}
    assert any(s["stage"] == "extract" for s in stages)


def test_pipeline_skip_extraction():
    settings = load_settings()
    from billing_agent.services.ocr_client import OcrClient

    ocr = OcrService(OcrClient(settings.ocr), url_provider=None)
    pipeline = BillingPipeline(settings, ocr_service=ocr, extraction_agent=_FakeAgent())  # type: ignore[arg-type]
    result = pipeline.run(
        [UploadedFile(name="synthetic_skip.pdf", data=sb.pdf_bytes())],
        skip_extraction=True,
        enable_ocr_upload=False,
    )
    assert result.outcomes
    assert result.outcomes[0].extract_error == "Extraction skipped"
    assert result.delivery_json == []
    assert any("OCR upload disabled" in w for w in result.warnings)


def test_pipeline_ocr_upload_default_off_even_if_oss_configured():
    settings = load_settings()
    stages = []
    pipeline = BillingPipeline(
        settings,
        extraction_agent=_FakeAgent(),  # type: ignore[arg-type]
        on_stage=lambda s, st, ev: stages.append(ev),
    )
    result = pipeline.run(
        [UploadedFile(name="synthetic_no_ocr.pdf", data=sb.pdf_bytes())],
        enable_ocr_upload=False,
    )
    assert any(s.get("stage") == "ocr" and s.get("status") == "skipped" for s in stages)
    ocr = result.outcomes[0].document.ocr
    assert ocr is not None
    assert ocr.status == OcrStatus.NOT_APPLICABLE
    assert ocr.error_code == "OCR_NOT_AUTHORIZED"
    # Text-layer PDF should not look like a failed parse when OCR was simply not authorized.
    from billing_agent.schemas import ParseStatus

    assert result.outcomes[0].document.status == ParseStatus.PARSED
