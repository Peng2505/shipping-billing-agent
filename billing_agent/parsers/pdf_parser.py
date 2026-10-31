"""PDF parser: embedded text layer and tables (PyMuPDF) plus the assignment OCR API.

The text layer is kept with origin=text_layer. It is evidence for cross-checking
and is never presented as an OCR result.
"""

from __future__ import annotations

import fitz

from billing_agent.parsers.ocr_blocks import run_ocr
from billing_agent.schemas import BlockKind, OcrStatus, ParsedDocument, ParseStatus, SourceOrigin

MAX_PAGES = 50


def _clean_cell(value) -> str:
    return "" if value is None else " ".join(str(value).split())


def expand_stacked_row(row: list) -> list[list[str]]:
    """Split a row whose cells all hold the same number (>1) of stacked lines into separate rows.

    PDF table detection sometimes returns several visual lines as one row with
    newline-joined cells. When line counts disagree (e.g. a wrapped description)
    the row is kept as a single row.
    """
    split = [[ln.strip() for ln in str(c).split("\n") if ln.strip()] if c else [] for c in row]
    counts = {len(lines) for lines in split if lines}
    if len(counts) == 1 and (n := counts.pop()) > 1:
        return [[lines[i] if lines else "" for lines in split] for i in range(n)]
    return [[_clean_cell(c) for c in row]]


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    with fitz.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass:
            doc.status = ParseStatus.FAILED
            doc.errors.append("PDF is password protected.")
            return
        doc.meta["page_count"] = pdf.page_count
        doc.meta["producer"] = (pdf.metadata or {}).get("producer")
        if pdf.page_count > MAX_PAGES:
            doc.warnings.append(f"Only the first {MAX_PAGES} of {pdf.page_count} pages were read.")

        pages_without_text = []
        for page_no, page in enumerate(pdf, start=1):
            if page_no > MAX_PAGES:
                break
            text = page.get_text("text").strip()
            image_count = len(page.get_images())
            if text:
                doc.add_block(BlockKind.PAGE_TEXT, SourceOrigin.TEXT_LAYER, "t", text,
                              page=page_no, meta={"image_count": image_count})
            else:
                pages_without_text.append(page_no)
            try:
                tables = page.find_tables().tables
            except Exception as exc:  # table detection is best effort
                doc.warnings.append(f"Table detection failed on page {page_no}: {type(exc).__name__}")
                tables = []
            for t_idx, table in enumerate(tables, start=1):
                rows = [r for row in table.extract() for r in expand_stacked_row(row)]
                rows = [r for r in rows if any(r)]
                if rows:
                    doc.add_block(
                        BlockKind.TABLE, SourceOrigin.TEXT_LAYER, "tb",
                        "\n".join(" | ".join(r) for r in rows),
                        page=page_no, table=rows, meta={"table_index": t_idx},
                    )
        if pages_without_text:
            doc.meta["pages_without_text_layer"] = pages_without_text
            doc.warnings.append(f"Pages without text layer (scanned?): {pages_without_text}")

    outcome = run_ocr(doc, data, ctx, ".pdf")
    has_text_layer = bool(doc.blocks_by_origin(SourceOrigin.TEXT_LAYER))
    if outcome.status == OcrStatus.SUCCESS:
        pass
    elif has_text_layer and outcome.status == OcrStatus.NOT_APPLICABLE:
        # Text layer succeeded; OCR intentionally not run — not a parse failure.
        doc.status = ParseStatus.PARSED
    elif has_text_layer:
        doc.status = ParseStatus.PARTIAL
        doc.warnings.append(
            "OCR result unavailable; only the PDF text layer (origin=text_layer) is present."
        )
    else:
        doc.status = ParseStatus.FAILED
        doc.errors.append("No text layer and no OCR result: document content is unavailable.")
