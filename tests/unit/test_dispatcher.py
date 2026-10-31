import json

import pytest

import synthetic_builders as sb
from billing_agent.config import LimitSettings
from billing_agent.parsers import ParseContext, detect_type, parse_bytes
from billing_agent.schemas import DocType, ParseStatus


@pytest.mark.parametrize("builder, expected", [
    (sb.pdf_bytes, DocType.PDF),
    (sb.png_bytes, DocType.PNG),
    (sb.jpg_bytes, DocType.JPG),
    (sb.tiff_bytes, DocType.TIFF),
    (sb.xlsx_bytes, DocType.XLSX),
    (sb.xls_bytes, DocType.XLS),
    (sb.docx_bytes, DocType.DOCX),
    (sb.bills_json_bytes, DocType.JSON),
    (sb.eml_bytes, DocType.EML),
])
def test_detects_type_by_content(builder, expected):
    assert detect_type(builder()) == expected


def test_unknown_content():
    assert detect_type(b"hello world, just text") == DocType.UNKNOWN
    assert detect_type(b"PK\x03\x04not a zip") == DocType.UNKNOWN


def test_content_wins_over_extension_with_warning():
    doc = parse_bytes(sb.pdf_bytes(), "looks_like.xlsx")
    assert doc.detected_type == DocType.PDF
    assert doc.declared_type == DocType.XLSX
    assert any("parsed by content" in w for w in doc.warnings)


def test_unsupported_file_is_reported_not_dropped():
    doc = parse_bytes(b"plain notes", "notes.txt")
    assert doc.status == ParseStatus.UNSUPPORTED
    assert doc.errors


def test_size_limit_skips_file():
    ctx = ParseContext(limits=LimitSettings(max_file_bytes=100))
    doc = parse_bytes(sb.pdf_bytes(), "big.pdf", ctx)
    assert doc.status == ParseStatus.SKIPPED
    assert "size limit" in doc.errors[0]


def test_corrupt_file_fails_gracefully():
    doc = parse_bytes(b"%PDF-1.4 garbage", "broken.pdf")
    assert doc.status == ParseStatus.FAILED
    assert doc.errors


def test_doc_id_is_stable_for_same_content():
    a = parse_bytes(sb.bills_json_bytes(), "a.json")
    b = parse_bytes(sb.bills_json_bytes(), "b.json")
    assert a.doc_id == b.doc_id
    assert a.sha256 == b.sha256


def test_json_parser_flags_synthetic():
    doc = parse_bytes(sb.bills_json_bytes(), "synthetic_bills.json")
    assert doc.meta["synthetic"] is True
    assert json.loads(doc.blocks[0].text)[0]["bill_id"] == "SYN-B-1"
