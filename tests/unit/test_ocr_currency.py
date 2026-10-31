"""OCR currency recovery: only from explicit OCR fields; never invent USD."""

from __future__ import annotations

import json

from billing_agent.agents.document_index import DocumentIndex
from billing_agent.agents.grounding import ground_extraction
from billing_agent.business.ocr_charge_filter import classify_ocr_charge_item
from billing_agent.business.ocr_currency import (
    currency_from_ocr_charge_item,
    document_currency_from_ocr_payload,
    inherit_currency_onto_charges,
)
from billing_agent.schemas import (
    BlockKind,
    ChargeNature,
    DocType,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    ParseStatus,
    ParsedDocument,
    SourceBlock,
    SourceOrigin,
)


def test_charge_ctr_is_not_currency():
    assert currency_from_ocr_charge_item({
        "chargeItem": "WHARFAGE",
        "amount": "21.90",
        "chargeCtr": "",
    }) is None
    assert currency_from_ocr_charge_item({
        "chargeItem": "WHARFAGE",
        "amount": "21.90",
        "chargeCtr": "JXLU4594463",
    }) is None


def test_currency_from_explicit_ocr_field():
    assert currency_from_ocr_charge_item({
        "chargeItem": "WHARFAGE",
        "amount": "21.90",
        "currency": "USD",
    }) == "USD"
    assert currency_from_ocr_charge_item({
        "chargeItem": "WHARFAGE",
        "amount": "USD 21.90",
    }) == "USD"


def test_zim_like_ocr_payload_has_no_currency():
    payload = {
        "fileType": "PAI-ZIM-NOTICE",
        "chargeList": [
            {"chargeItem": "WHARFAGE ADMINISTRATION FEE", "amount": "5.00", "chargeCtr": ""},
            {"chargeItem": "WHARFAGE", "amount": "21.90", "chargeCtr": ""},
        ],
    }
    assert document_currency_from_ocr_payload(payload, block_id="o1") is None
    filtered = classify_ocr_charge_item(payload["chargeList"][0], block_id="o1")
    assert filtered.keep_as_line
    assert filtered.charge.currency is None


def test_inherit_only_when_document_currency_evidenced():
    charges = [
        ExtractedCharge(
            raw_name="WHARFAGE", nature=ChargeNature.ACTUAL, amount="21.90", currency=None,
        )
    ]
    assert inherit_currency_onto_charges(charges, None)[0].currency is None
    out = inherit_currency_onto_charges(
        charges, EvidencedValue(value="USD", evidence=[]),
    )
    assert out[0].currency == "USD"


def test_grounding_inherits_usd_when_ocr_json_has_currency():
    item = {
        "invoiceNumber": "QRF1",
        "chargeList": [
            {"chargeItem": "WHARFAGE", "amount": "21.90", "currency": "USD", "chargeCtr": ""},
        ],
    }
    doc = ParsedDocument(
        doc_id="D0",
        file_name="zim.png",
        source_chain=["zim.png"],
        declared_type=DocType.PNG,
        detected_type=DocType.PNG,
        sha256="a" * 64,
        size_bytes=10,
        status=ParseStatus.PARSED,
        blocks=[
            SourceBlock(
                block_id="D0:o1",
                kind=BlockKind.OCR_RESULT,
                origin=SourceOrigin.OCR_API,
                text=json.dumps(item, ensure_ascii=False),
            )
        ],
    )
    # Agent returns no evidenced charges → OCR chargeList becomes the source.
    raw = ExtractionResult(charges=[], currency=None)
    grounded = ground_extraction(raw, DocumentIndex.from_document(doc))
    assert grounded.result.currency is not None
    assert grounded.result.currency.value == "USD"
    assert grounded.actual_charges
    assert grounded.actual_charges[0].currency == "USD"


def test_grounding_keeps_null_when_zim_ocr_omits_currency():
    item = {
        "fileType": "PAI-ZIM-NOTICE",
        "invoiceNumber": "QRF1618731",
        "chargeList": [
            {"chargeItem": "WHARFAGE ADMINISTRATION FEE", "amount": "5.00", "chargeCtr": ""},
            {"chargeItem": "WHARFAGE", "amount": "21.90", "chargeCtr": ""},
        ],
    }
    doc = ParsedDocument(
        doc_id="D0",
        file_name="图片示例.png",
        source_chain=["图片示例.png"],
        declared_type=DocType.PNG,
        detected_type=DocType.PNG,
        sha256="b" * 64,
        size_bytes=10,
        status=ParseStatus.PARSED,
        blocks=[
            SourceBlock(
                block_id="D0:o1",
                kind=BlockKind.OCR_RESULT,
                origin=SourceOrigin.OCR_API,
                text=json.dumps(item, ensure_ascii=False),
            )
        ],
    )
    raw = ExtractionResult(
        charges=[
            ExtractedCharge(
                raw_name="WHARFAGE ADMINISTRATION FEE",
                nature=ChargeNature.ACTUAL,
                amount="5.00",
                currency=None,
                evidence=[],
            ),
            ExtractedCharge(
                raw_name="WHARFAGE",
                nature=ChargeNature.ACTUAL,
                amount="21.90",
                currency=None,
                evidence=[],
            ),
        ],
    )
    grounded = ground_extraction(raw, DocumentIndex.from_document(doc))
    assert grounded.result.currency is None or grounded.result.currency.value is None
    assert all(c.currency is None for c in grounded.actual_charges)
    assert any("no explicit ISO currency" in w for w in grounded.result.warnings)
