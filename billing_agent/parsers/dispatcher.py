"""File type detection (magic bytes first) and dispatch to format parsers."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from billing_agent.config import LimitSettings
from billing_agent.schemas import DocType, ParsedDocument, ParseStatus
from billing_agent.security import SecurityError, check_size, file_extension, sanitize_filename, sha256_hex
from billing_agent.services.ocr_service import OcrService

logger = logging.getLogger(__name__)

EXTENSION_TYPES = {
    "eml": DocType.EML,
    "pdf": DocType.PDF,
    "png": DocType.PNG,
    "jpg": DocType.JPG,
    "jpeg": DocType.JPG,
    "tif": DocType.TIFF,
    "tiff": DocType.TIFF,
    "xlsx": DocType.XLSX,
    "xls": DocType.XLS,
    "docx": DocType.DOCX,
    "doc": DocType.DOC,
    "json": DocType.JSON,
}
SUPPORTED_EXTENSIONS = sorted(EXTENSION_TYPES)

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_EMAIL_HEADER = re.compile(
    rb"^(received|from|to|subject|date|mime-version|message-id|return-path|content-type|x-[\w-]+):",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParseContext:
    limits: LimitSettings = field(default_factory=LimitSettings)
    ocr_service: OcrService | None = None
    soffice_path: str = ""
    depth: int = 0
    attachment_counter: list[int] = field(default_factory=lambda: [0])

    def child(self) -> ParseContext:
        return ParseContext(
            limits=self.limits,
            ocr_service=self.ocr_service,
            soffice_path=self.soffice_path,
            depth=self.depth + 1,
            attachment_counter=self.attachment_counter,
        )


def detect_type(data: bytes, filename: str = "") -> DocType:
    head = data[:8]
    if head.startswith(b"%PDF"):
        return DocType.PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return DocType.PNG
    if head.startswith(b"\xff\xd8\xff"):
        return DocType.JPG
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return DocType.TIFF
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            return DocType.UNKNOWN
        if "word/document.xml" in names:
            return DocType.DOCX
        if "xl/workbook.xml" in names:
            return DocType.XLSX
        return DocType.UNKNOWN
    if head.startswith(_OLE_MAGIC):
        if "WordDocument".encode("utf-16-le") in data:
            return DocType.DOC
        if "Workbook".encode("utf-16-le") in data or "Book".encode("utf-16-le") in data:
            return DocType.XLS
        return DocType.UNKNOWN

    stripped = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped[:1] in (b"{", b"["):
        try:
            json.loads(stripped.decode("utf-8"))
            return DocType.JSON
        except (UnicodeDecodeError, ValueError):
            pass
    header_zone = data[:8192].split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0]
    if len(_EMAIL_HEADER.findall(header_zone)) >= 2:
        return DocType.EML
    return DocType.UNKNOWN


def _declared_type(filename: str) -> DocType:
    return EXTENSION_TYPES.get(file_extension(filename), DocType.UNKNOWN)


def _parser_for(doc_type: DocType):
    from billing_agent.parsers import (
        email_parser,
        excel_parser,
        image_parser,
        json_parser,
        pdf_parser,
        word_parser,
    )

    return {
        DocType.EML: email_parser.parse,
        DocType.PDF: pdf_parser.parse,
        DocType.PNG: image_parser.parse,
        DocType.JPG: image_parser.parse,
        DocType.TIFF: image_parser.parse,
        DocType.XLSX: excel_parser.parse,
        DocType.XLS: excel_parser.parse,
        DocType.DOCX: word_parser.parse,
        DocType.DOC: word_parser.parse,
        DocType.JSON: json_parser.parse,
    }.get(doc_type)


def parse_bytes(
    data: bytes,
    filename: str,
    ctx: ParseContext | None = None,
    *,
    source_chain: list[str] | None = None,
    declared_mime: str | None = None,
    position: str = "0",
) -> ParsedDocument:
    ctx = ctx or ParseContext()
    safe_name = sanitize_filename(filename)
    digest = sha256_hex(data)
    detected = detect_type(data, safe_name)
    declared = _declared_type(safe_name)
    doc = ParsedDocument(
        doc_id=f"D{position}-{digest[:8]}",
        file_name=safe_name,
        source_chain=[*(source_chain or []), safe_name],
        declared_type=declared,
        detected_type=detected,
        declared_mime=declared_mime,
        sha256=digest,
        size_bytes=len(data),
    )

    try:
        check_size(len(data), ctx.limits.max_file_bytes, f"File '{safe_name}'")
    except SecurityError as exc:
        doc.status = ParseStatus.SKIPPED
        doc.errors.append(str(exc))
        return doc

    if declared not in (DocType.UNKNOWN, detected) and detected != DocType.UNKNOWN:
        doc.warnings.append(
            f"Extension suggests '{declared.value}' but content is '{detected.value}'; parsed by content."
        )

    parser = _parser_for(detected)
    if parser is None:
        doc.status = ParseStatus.UNSUPPORTED
        doc.errors.append(f"Unsupported or unrecognised file content (extension '{declared.value}').")
        return doc

    try:
        parser(doc, data, ctx)
    except Exception as exc:  # parser bugs or corrupt files must not stop the batch
        logger.exception("Parser failed for %s", doc.doc_id)
        doc.status = ParseStatus.FAILED
        doc.errors.append(f"{detected.value} parser error: {type(exc).__name__}: {str(exc)[:200]}")
    return doc


def parse_path(path: str | Path, ctx: ParseContext | None = None, position: str = "0") -> ParsedDocument:
    path = Path(path)
    ctx = ctx or ParseContext()
    size = path.stat().st_size
    if size > ctx.limits.max_file_bytes:
        doc = parse_bytes(b"", path.name, ctx, position=position)
        doc.size_bytes = size
        doc.status = ParseStatus.SKIPPED
        doc.errors = [f"File '{doc.file_name}' exceeds the size limit ({size} > {ctx.limits.max_file_bytes} bytes)"]
        return doc
    return parse_bytes(path.read_bytes(), path.name, ctx, position=position)
