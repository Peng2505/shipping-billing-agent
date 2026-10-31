"""Regression: Arrival Notice payment direction must not flip Consignee into AR."""

from __future__ import annotations

from billing_agent.business.ar_ap_classifier import classify_ar_ap
from billing_agent.business.decision_engine import decide_for_document
from billing_agent.business.payment_direction import extract_payment_direction
from billing_agent.schemas import (
    BillRecord,
    ChargeNature,
    EvidenceRef,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    OperationType,
)


PDF1_LIKE_TEXT = """
GENERAL NOTICE
NEPTUNE SHIPPING LIMITED
17800 CASTLETON STREET, SUITE 300
CITY OF INDUSTRY, CA 91748
Please Pay freight against the master B/L shown below
TOTAL CHARGES TO BE PAID:
 245.0000
SHIPPER
CIMC WETRANS INTL LOG CO LTD
CONSIGNEE
NEPTUNE SHIPPING LIMITED
REMIT TO
CMA CGM (AMERICA) LLC
ONE CMA CGM WAY
NORFOLK, VA
Beneficiary: CMA CGM & ANL Securities BV
HSBC Bank USA NA
"""


def test_extract_payment_direction_pdf1_like():
    ev = extract_payment_direction(PDF1_LIKE_TEXT)
    assert ev.strong
    assert any("CMA CGM (AMERICA) LLC" in p.upper() for p in ev.payees)
    assert any("NEPTUNE" in p.upper() for p in ev.payers)
    assert not any("HSBC" in p.upper() for p in ev.payees)
    assert not any(p.upper() == "SECURITIES BV" for p in ev.payees)


def test_extract_payment_direction_broken_remit_layout():
    """Real PDF1 text layer: REMIT TO then party headers; company+address later."""
    text = """
Please Pay freight against the master B/L shown below
TOTAL CHARGES TO BE PAID: 245.0000
CONSIGNEE
NEPTUNE SHIPPING LIMITED
DBA CMA-CGM Beneficiary: CMA CGM & ANL Securities BV
HSBC Bank USA NA
REMIT TO
SHIPPER
NOTIFY
CONSIGNEE
GENERAL NOTICE
NEPTUNE SHIPPING LIMITED
BENEFICIARY: CMACGM & ANL
SECURITIES BV
HSBC BANK USA, N.A.
ACCT #: 000279331
CMA CGM (AMERICA) LLC
ONE CMA CGM WAY
NORFOLK, VA
UNITED STATES
"""
    ev = extract_payment_direction(text)
    assert ev.strong
    assert any("CMA CGM (AMERICA) LLC" in p.upper() for p in ev.payees)
    assert any("NEPTUNE" in p.upper() for p in ev.payers)
    assert not any(p.upper() == "SECURITIES BV" for p in ev.payees)


def test_neptune_as_accounting_entity_is_ap_not_ar():
    """Even if LLM wrongly sets issuer=Neptune, payment hints force AP."""
    ev = extract_payment_direction(PDF1_LIKE_TEXT)
    bill = BillRecord(
        document_type="Arrival Notice / Freight Bill (General Notice)",
        issuer="NEPTUNE SHIPPING LIMITED",  # incorrect LLM role
        recipient="CIMC WETRANS INTL LOG CO LTD",
        charge_item="On Carriage Additional - US Em",
        amount="245.0000",
        currency="USD",
    )
    wrong = classify_ar_ap(bill, "NEPTUNE SHIPPING LIMITED")
    assert wrong.posting_type == "AR"  # naive issuer=payee path (baseline bug)

    fixed = classify_ar_ap(
        bill,
        "NEPTUNE SHIPPING LIMITED",
        payee_hints=ev.payees,
        payer_hints=ev.payers,
        prefer_payment_hints=True,
    )
    assert fixed.posting_type == "AP"
    assert not fixed.needs_review


def test_decide_create_ap_with_payment_hints():
    grounded = GroundedExtraction(
        result=ExtractionResult(
            document_type=EvidencedValue(value="Arrival Notice"),
            issuer=EvidencedValue(value="NEPTUNE SHIPPING LIMITED"),
            recipient=EvidencedValue(value="CIMC WETRANS INTL LOG CO LTD"),
        ),
        actual_charges=[
            ExtractedCharge(
                raw_name="On Carriage Additional - US Em",
                nature=ChargeNature.ACTUAL,
                amount="245.0000",
                currency="USD",
                evidence=[EvidenceRef(block_id="b", quote="On Carriage Additional - US Em 245.0000")],
            )
        ],
    )
    ev = extract_payment_direction(PDF1_LIKE_TEXT)
    decisions = decide_for_document(
        grounded,
        [],
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="pdf1",
        payee_hints=ev.payees,
        payer_hints=ev.payers,
        prefer_payment_hints=True,
    )
    assert len(decisions) == 1
    assert decisions[0].operation == OperationType.CREATE
    assert decisions[0].posting_type == "AP"
