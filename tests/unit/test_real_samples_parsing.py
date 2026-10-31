"""Phase 1 parsing checks on the recruiter samples (read-only, no external calls).

OCR is deliberately NOT configured here, so these tests also prove that missing
OCR is reported honestly. Real OCR checks live in tests/integration.
"""

import hashlib

import pytest

from billing_agent.parsers import ParseContext, parse_path
from billing_agent.schemas import BlockKind, DocType, OcrStatus, SourceOrigin
from conftest import SAMPLES_DIR, find_sample


def _top_level_sample_files():
    """Recruiter sample files at data/samples/ root (exclude subdirs like synthetic_exam/)."""
    return sorted(p for p in SAMPLES_DIR.iterdir() if p.is_file())


@pytest.fixture(scope="module")
def sample_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in _top_level_sample_files()}


def test_all_four_samples_present():
    names = sorted(p.suffix.lower() for p in _top_level_sample_files())
    assert names == [".eml", ".pdf", ".pdf", ".png"]


def test_eml_sample(expected):
    exp = expected["eml_pre_alert"]["parsing"]
    doc = parse_path(find_sample(expected["eml_pre_alert"]["file_glob"]), ParseContext())
    assert doc.detected_type == DocType.EML
    for token in exp["subject_contains"]:
        assert token in doc.email.subject
    assert exp["from_contains"] in doc.email.sender
    assert any(exp["to_contains"] in t for t in doc.email.to)
    plain = next(b for b in doc.blocks if b.meta.get("content_type") == "text/plain").text
    for token in exp["body_plain_contains"]:
        assert token in plain
    assert doc.email.body_html_present is exp["body_html_present"]

    attachments = [c for c in doc.children if not c.meta["inline"]]
    inline = [c for c in doc.children if c.meta["inline"]]
    assert [a.file_name for a in attachments] == [a["file_name"] for a in exp["attachments"]]
    for child, exp_att in zip(attachments, exp["attachments"]):
        assert child.meta["original_filename"].replace("\xa0", " ") == exp_att["file_name"]
        assert child.declared_mime == exp_att["declared_mime"]
        assert child.detected_type.value == exp_att["detected_type"]
        text = child.text_by_origin(SourceOrigin.TEXT_LAYER)
        for token in exp_att["text_contains"]:
            assert token in text
        assert child.source_chain[0] == doc.file_name
    assert [(c.file_name, c.detected_type.value) for c in inline] == [
        (i["file_name"], i["detected_type"]) for i in exp["inline_images"]
    ]
    assert inline[0].ocr.status == OcrStatus.NOT_CONFIGURED


@pytest.mark.parametrize("key", ["pdf_sample_1", "pdf_sample_2"])
def test_pdf_samples(expected, key):
    exp = expected[key]
    doc = parse_path(SAMPLES_DIR / exp["file_name"], ParseContext())
    assert doc.detected_type.value == exp["parsing"]["detected_type"]
    assert doc.meta["page_count"] == exp["parsing"]["page_count"]
    text = doc.text_by_origin(SourceOrigin.TEXT_LAYER)
    for token in exp["parsing"]["text_layer_contains"]:
        assert token in text
    assert doc.ocr.status == OcrStatus.NOT_CONFIGURED
    assert not doc.blocks_by_origin(SourceOrigin.OCR_API)


def test_pdf2_charge_table_rows_are_separate(expected):
    exp = expected["pdf_sample_2"]
    doc = parse_path(SAMPLES_DIR / exp["file_name"], ParseContext())
    tables = [b.table for b in doc.blocks if b.kind == BlockKind.TABLE]
    charge_table = next(t for t in tables if t[0][0] == "DESCRIPTION")
    descriptions = [row[0] for row in charge_table[1:]]
    assert descriptions == [c["raw_name"] for c in exp["extraction"]["charges"]]


def test_png_sample_requires_ocr(expected):
    exp = expected["png_sample"]
    doc = parse_path(SAMPLES_DIR / exp["file_name"], ParseContext())
    assert doc.detected_type.value == exp["parsing"]["detected_type"]
    assert doc.blocks == []
    assert doc.ocr.status == OcrStatus.NOT_CONFIGURED


def test_parsing_does_not_modify_samples(sample_hashes):
    for path in _top_level_sample_files():
        parse_path(path, ParseContext())
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in _top_level_sample_files()}
    assert after == sample_hashes
