"""Phase 3 deterministic business-rule tests (synthetic fixtures only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from billing_agent.business.ar_ap_classifier import classify_ar_ap
from billing_agent.business.bill_matcher import BillMatcher
from billing_agent.business.bill_store import load_bills_path
from billing_agent.business.bill_updater import build_update
from billing_agent.business.currency import normalize_currency
from billing_agent.business.date_parser import parse_document_date
from billing_agent.business.decision_engine import decide_for_document
from billing_agent.business.json_builder import build_processing_result, dumps_delivery_json, validate_delivery_json
from billing_agent.business.payment_term import normalize_payment_term
from billing_agent.business.validator import fingerprint_for, iso6346_check_digit, validate_container
from billing_agent.schemas import (
    BillRecord,
    ChangeRequest,
    ChargeNature,
    EvidenceRef,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    OperationType,
)

FIXTURE = Path(__file__).resolve().parents[1].parent / "data" / "fixtures" / "synthetic" / "synthetic_existing_bills.json"


@pytest.fixture(scope="module")
def existing():
    bills = load_bills_path(FIXTURE)
    assert all(b.synthetic for b in bills)
    return bills


def test_currency_symbol_rejected():
    assert normalize_currency("$") == (None, "symbol_not_iso4217")
    assert normalize_currency("USD") == ("USD", None)


def test_payment_term_mapping():
    assert normalize_payment_term("FREIGHT PREPAID").standard == "PP"
    assert normalize_payment_term("C").standard == "CC"
    assert normalize_payment_term("PAY IMMEDIATELY").standard is None
    assert normalize_payment_term("COD").standard is None


def test_date_mdy_from_sibling_evidence():
    # 08-30-2026 proves MDY in the same file
    result = parse_document_date("10-24-2026", sibling_raw_dates=["08-30-2026", "10-28-2026"])
    assert result.value.isoformat() == "2026-10-24"
    assert result.ambiguous is False


def test_date_ambiguous_without_evidence():
    result = parse_document_date("10/03/2025", sibling_raw_dates=["03/10/2025"])
    assert result.value is None and result.ambiguous


def test_iso6346_sample_containers():
    for code in ["TIIU8975975", "SAPU2040689", "MRSU2571577", "JXLU4504463"]:
        assert iso6346_check_digit(code) == int(code[-1])
        assert validate_container(code) == []


def test_l1_unique_match(existing):
    incoming = BillRecord(
        reference_no="DC-108478",
        charge_item="4 ADD'L DETENTION FREE TIME CHARGE",
        amount="1310.40", currency="USD",
    )
    result = BillMatcher().match(incoming, existing)
    assert result.status == "matched" and result.bill_id == "SYN-BILL-DET-1310"


def test_two_handling_charges_ambiguous_without_non_amount_evidence(existing):
    incoming = BillRecord(
        reference_no="DC-108478",
        charge_item="Handling Charge",
        amount="65.00", currency="USD",
    )
    result = BillMatcher().match(incoming, existing)
    assert result.status == "ambiguous"
    assert set(result.candidate_ids) == {"SYN-BILL-HC-65", "SYN-BILL-HC-35"}


def test_two_handling_charges_disambiguated_by_line_hint_not_amount(existing):
    incoming = BillRecord(
        reference_no="DC-108478",
        charge_item="Handling Charge",
        amount="999.00",  # deliberately wrong — amount must not be sole key
        currency="USD",
        extra={"line_hint": "1"},
    )
    result = BillMatcher().match(incoming, existing)
    assert result.status == "matched"
    assert result.bill_id == "SYN-BILL-HC-65"


def test_same_bill_not_claimed_twice(existing):
    matcher = BillMatcher()
    first = BillMatcher().match  # noqa: keep separate matchers for clarity
    m = BillMatcher()
    a = BillRecord(reference_no="INV-SYN-001", charge_item="Documentation Fee", currency="USD", amount="40")
    r1 = m.match(a, existing)
    r2 = m.match(a, existing)
    assert r1.status == "matched"
    assert r2.status == "none"  # claimed


def test_update_keeps_unmentioned_fields(existing):
    bill = next(b for b in existing if b.bill_id == "SYN-BILL-DOC-40")
    incoming = BillRecord(amount="45.00", currency="USD", charge_item="Documentation Fee")
    updated, changes, unresolved = build_update(
        bill, incoming,
        change_requests=[ChangeRequest(
            field="amount", new_value="45.00",
            evidence=[EvidenceRef(block_id="x", quote="amend to 45.00")],
        )],
    )
    assert updated.amount == "45.00"
    assert updated.payment_term == "PP"  # preserved
    assert updated.bl_no == "BL-SYN-001"
    assert [c.field for c in changes] == ["amount"]


def test_ar_ap_not_from_debit_note_alone():
    bill = BillRecord(
        document_type="Debit Note",
        issuer="NEPTUNE SHIPPING LIMITED",
        recipient="SOME CUSTOMER",
    )
    # Without accounting_entity match reliability
    r = classify_ar_ap(bill, "Unrelated Entity Co")
    assert r.posting_type is None and r.needs_review

    r2 = classify_ar_ap(bill, "NEPTUNE SHIPPING LIMITED")
    assert r2.posting_type == "AR" and not r2.needs_review

    r3 = classify_ar_ap(bill, "SOME CUSTOMER")
    assert r3.posting_type == "AP"


def test_decision_create_and_json(existing):
    grounded = GroundedExtraction(
        result=ExtractionResult(document_type=None),
        actual_charges=[
            ExtractedCharge(
                raw_name="Trucking Fee", nature=ChargeNature.ACTUAL,
                amount="120.00", currency="USD",
                evidence=[EvidenceRef(block_id="b", quote="Trucking Fee USD 120.00")],
            )
        ],
    )
    # Patch evidenced document fields via result
    grounded.result.document_type = type("E", (), {"value": "Invoice", "evidence": []})()
    from billing_agent.schemas import EvidencedValue
    grounded.result.document_type = EvidencedValue(value="Invoice")
    grounded.result.issuer = EvidencedValue(value="Truck Co")
    grounded.result.recipient = EvidencedValue(value="Shipper Co")

    decisions = decide_for_document(
        grounded, existing,
        accounting_entity="Shipper Co",
        file_sha256="abc",
    )
    assert len(decisions) == 1
    assert decisions[0].operation == OperationType.CREATE
    assert decisions[0].posting_type == "AP"
    result = build_processing_result(decisions)
    text = dumps_delivery_json(result)
    ok, errors = validate_delivery_json(text)
    assert ok, errors
    assert '"operation": "CREATE"' in text


def test_decision_pending_on_dollar_currency():
    from billing_agent.schemas import EvidencedValue
    grounded = GroundedExtraction(
        result=ExtractionResult(
            document_type=EvidencedValue(value="Pre-Alert"),
        ),
        actual_charges=[
            ExtractedCharge(
                raw_name="H/C", nature=ChargeNature.ACTUAL, amount="50", currency=None,
                evidence=[EvidenceRef(block_id="b", quote="H/C $50")],
            )
        ],
    )
    decisions = decide_for_document(grounded, [], accounting_entity="X", file_sha256="x")
    assert decisions[0].operation == OperationType.PENDING_REVIEW
    assert any(i.code == "CURRENCY_UNCONFIRMED" for i in decisions[0].validation_issues)


def test_idempotent_fingerprint():
    a = fingerprint_for(file_sha256="f", line_index=0, charge_name="Handling Charge",
                        amount="65.00", currency="USD", reference_no="DC-1")
    b = fingerprint_for(file_sha256="f", line_index=0, charge_name="HANDLING CHARGE",
                        amount="65.00", currency="USD", reference_no="DC-1")
    c = fingerprint_for(file_sha256="f", line_index=1, charge_name="Handling Charge",
                        amount="65.00", currency="USD", reference_no="DC-1")
    assert a == b and a != c
