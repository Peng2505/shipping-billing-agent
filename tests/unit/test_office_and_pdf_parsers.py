import pytest

import synthetic_builders as sb
from billing_agent.parsers import ParseContext, parse_bytes
from billing_agent.parsers.pdf_parser import expand_stacked_row
from billing_agent.parsers import word_parser
from billing_agent.schemas import BlockKind, DocType, OcrStatus, ParseStatus, SourceOrigin


def test_xlsx_rows_and_decimal_safe_numbers():
    doc = parse_bytes(sb.xlsx_bytes(), "s.xlsx")
    assert doc.status == ParseStatus.PARSED
    assert len(doc.blocks) == 1  # empty sheet is skipped
    table = doc.blocks[0].table
    assert table[0][0] == sb.SYNTHETIC_MARK
    assert table[2] == ["Doc Fee", "1", "35.5", "35.5", "USD"]
    assert table[3][3] == "1310.4"
    assert doc.blocks[0].meta["sheet"] == "Charges"


def test_xls_rows():
    doc = parse_bytes(sb.xls_bytes(), "s.xls")
    assert doc.detected_type == DocType.XLS
    assert doc.blocks[0].table[2] == ["Trucking Fee", "1", "120.75", "CNY"]


def test_docx_paragraphs_and_tables_in_order():
    doc = parse_bytes(sb.docx_bytes(), "d.docx")
    kinds = [b.kind for b in doc.blocks]
    assert kinds == [BlockKind.PARAGRAPHS, BlockKind.TABLE, BlockKind.PARAGRAPHS]
    assert doc.blocks[1].table[1] == ["Storage Fee", "80.00", "USD"]
    assert "Total USD 125.00" in doc.blocks[2].text


def test_doc_without_libreoffice_fails_explicitly(monkeypatch):
    monkeypatch.setattr(word_parser, "find_soffice", lambda configured="": None)
    fake_doc = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + "WordDocument".encode("utf-16-le") + b"\x00" * 64
    doc = parse_bytes(fake_doc, "legacy.doc")
    assert doc.detected_type == DocType.DOC
    assert doc.status == ParseStatus.FAILED
    assert "LibreOffice" in doc.errors[0]


def test_pdf_text_layer_is_not_reported_as_ocr():
    doc = parse_bytes(sb.pdf_bytes(), "x.pdf", ParseContext())
    assert doc.blocks[0].origin == SourceOrigin.TEXT_LAYER
    assert doc.ocr.status == OcrStatus.NOT_CONFIGURED
    assert doc.status == ParseStatus.PARTIAL
    assert not doc.blocks_by_origin(SourceOrigin.OCR_API)


def test_pdf_without_text_and_without_ocr_fails():
    doc = parse_bytes(sb.blank_pdf_bytes(), "scan.pdf", ParseContext())
    assert doc.status == ParseStatus.FAILED
    assert doc.meta["pages_without_text_layer"] == [1]


@pytest.mark.parametrize("row, expected", [
    (["A\nB\nC", "-\n-\n-", "1\n2\n3", ""], [["A", "-", "1", ""], ["B", "-", "2", ""], ["C", "-", "3", ""]]),
    (["Long description\nwrapped", "65.00"], [["Long description wrapped", "65.00"]]),
    (["single", None, "x"], [["single", "", "x"]]),
])
def test_expand_stacked_row(row, expected):
    assert expand_stacked_row(row) == expected
