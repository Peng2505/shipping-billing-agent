"""DOCX parser (python-docx). Legacy DOC is converted to DOCX with LibreOffice when available."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from billing_agent.schemas import BlockKind, DocType, ParsedDocument, ParseStatus, SourceOrigin

_SOFFICE_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]
CONVERT_TIMEOUT_SECONDS = 120


def find_soffice(configured: str = "") -> str | None:
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    return next((c for c in _SOFFICE_CANDIDATES if Path(c).is_file()), None)


def _unique_cells(row) -> list[str]:
    cells, seen = [], set()
    for cell in row.cells:
        if id(cell._tc) in seen:  # merged cells are repeated by python-docx
            continue
        seen.add(id(cell._tc))
        cells.append(" ".join(cell.text.split()))
    return cells


def _parse_docx(doc: ParsedDocument, data: bytes) -> None:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(data))
    paragraphs: list[str] = []
    table_index = 0

    def flush() -> None:
        if paragraphs:
            doc.add_block(BlockKind.PARAGRAPHS, SourceOrigin.NATIVE, "p", "\n".join(paragraphs))
            paragraphs.clear()

    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(element, document).text.strip()
            if text:
                paragraphs.append(text)
        elif tag == "tbl":
            flush()
            table_index += 1
            rows = [_unique_cells(r) for r in Table(element, document).rows]
            rows = [r for r in rows if any(r)]
            if rows:
                doc.add_block(
                    BlockKind.TABLE, SourceOrigin.NATIVE, "tb",
                    "\n".join(" | ".join(r) for r in rows),
                    table=rows, meta={"table_index": table_index},
                )
    flush()


def _convert_doc(data: bytes, soffice: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="sba_doc_") as tmp:
        src = Path(tmp) / "input.doc"
        src.write_bytes(data)
        subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "docx", "--outdir", tmp, str(src)],
            check=True, capture_output=True, timeout=CONVERT_TIMEOUT_SECONDS,
        )
        out = Path(tmp) / "input.docx"
        if not out.is_file():
            raise RuntimeError("LibreOffice did not produce a .docx file")
        return out.read_bytes()


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    if doc.detected_type == DocType.DOC:
        soffice = find_soffice(getattr(ctx, "soffice_path", ""))
        if not soffice:
            doc.status = ParseStatus.FAILED
            doc.errors.append(
                "Legacy .doc requires LibreOffice (soffice) for conversion, which is not installed "
                "or not configured via SOFFICE_PATH."
            )
            return
        data = _convert_doc(data, soffice)
        doc.meta["converted_by"] = "libreoffice"
    _parse_docx(doc, data)
    if not doc.blocks:
        doc.status = ParseStatus.PARTIAL
        doc.warnings.append("Word document contains no text or tables.")
