"""Attach a real OCR outcome to a ParsedDocument as `ocr_api` evidence blocks."""

from __future__ import annotations

import json

from billing_agent.schemas import BlockKind, OcrOutcome, OcrStatus, ParsedDocument, SourceOrigin


def run_ocr(doc: ParsedDocument, data: bytes, ctx, suffix: str) -> OcrOutcome:
    if ctx.ocr_service is None:
        outcome = OcrOutcome(
            status=OcrStatus.NOT_CONFIGURED,
            error_code="OCR_SERVICE_NOT_CONFIGURED",
            error_message="OCR service not configured; OCR was not called.",
        )
    else:
        outcome = ctx.ocr_service.recognize(data, suffix)
    doc.ocr = outcome

    if outcome.status == OcrStatus.SUCCESS and outcome.raw_response:
        data_obj = outcome.raw_response.get("data", {})
        for idx, item in enumerate(data_obj.get("list", [])):
            doc.add_block(
                BlockKind.OCR_RESULT,
                SourceOrigin.OCR_API,
                "o",
                json.dumps(item, ensure_ascii=False, indent=1),
                meta={
                    "list_index": idx,
                    "page_index": item.get("page_index") if isinstance(item, dict) else None,
                    "orderType": data_obj.get("orderType"),
                },
            )
        doc.warnings.extend(f"OCR: {w}" for w in outcome.warnings)
    elif outcome.status == OcrStatus.FAILED:
        doc.errors.append(f"OCR failed [{outcome.error_code}]: {outcome.error_message}")
    elif outcome.status == OcrStatus.NOT_APPLICABLE:
        # Intentional skip (e.g. operator did not authorize OCR) — informational only.
        doc.meta["ocr_skip_reason"] = outcome.error_code
    elif outcome.status == OcrStatus.NOT_CONFIGURED:
        doc.warnings.append(f"OCR not run [{outcome.error_code}]: {outcome.error_message}")
    return outcome
