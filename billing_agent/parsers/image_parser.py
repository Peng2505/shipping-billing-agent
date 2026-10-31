"""Image parser (PNG/JPG/TIFF). The assignment OCR API is the only text source."""

from __future__ import annotations

import io

from PIL import Image

from billing_agent.parsers.ocr_blocks import run_ocr
from billing_agent.schemas import DocType, OcrStatus, ParsedDocument, ParseStatus

_SUFFIX = {DocType.PNG: ".png", DocType.JPG: ".jpg", DocType.TIFF: ".tiff"}


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    with Image.open(io.BytesIO(data)) as img:
        img.verify()
    with Image.open(io.BytesIO(data)) as img:
        doc.meta.update({
            "width": img.width,
            "height": img.height,
            "image_format": img.format,
            "mode": img.mode,
            "frames": getattr(img, "n_frames", 1),
        })

    outcome = run_ocr(doc, data, ctx, _SUFFIX.get(doc.detected_type, ".png"))
    if outcome.status == OcrStatus.SUCCESS:
        doc.status = ParseStatus.PARSED
    elif outcome.status in {OcrStatus.NOT_CONFIGURED, OcrStatus.NOT_APPLICABLE}:
        doc.status = ParseStatus.PARTIAL
        doc.warnings.append(
            "No text extracted from image: OCR was not run "
            f"[{outcome.error_code or outcome.status.value}]."
        )
    else:
        doc.status = ParseStatus.FAILED
        doc.warnings.append("No text extracted from image: OCR result unavailable.")
