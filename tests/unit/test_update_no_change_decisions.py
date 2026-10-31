"""UPDATE / NO_CHANGE decision paths with evidenced change requests."""

from __future__ import annotations

from billing_agent.business.decision_engine import decide_for_document
from billing_agent.schemas import (
    BillRecord,
    ChangeRequest,
    ChargeNature,
    EvidenceRef,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    MatchLevel,
    OperationType,
)


def _grounded(amount: str, currency: str = "USD") -> GroundedExtraction:
    return GroundedExtraction(
        result=ExtractionResult(
            document_type=EvidencedValue(value="Debit Note"),
            issuer=EvidencedValue(value="NEPTUNE SHIPPING LIMITED"),
            recipient=EvidencedValue(value="ACME FREIGHT CONSIGNEE LLC"),
            reference_no=EvidencedValue(value="DC-1001"),
        ),
        actual_charges=[
            ExtractedCharge(
                raw_name="HANDLING CHARGE",
                nature=ChargeNature.ACTUAL,
                amount=amount,
                currency=currency,
                evidence=[EvidenceRef(block_id="b1", quote=f"HANDLING CHARGE {amount} {currency}")],
            )
        ],
    )


def test_no_change_when_unique_match_and_identical_fields():
    existing = [
        BillRecord(
            bill_id="b1",
            document_type="Debit Note",
            reference_no="DC-1001",
            issuer="NEPTUNE SHIPPING LIMITED",
            recipient="ACME FREIGHT CONSIGNEE LLC",
            charge_item="Handling Charge",
            charge_item_raw="HANDLING CHARGE",
            amount="125.50",
            currency="USD",
            accounting_entity="NEPTUNE SHIPPING LIMITED",
            posting_type="AR",
        )
    ]
    decisions = decide_for_document(
        _grounded("125.50"),
        existing,
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="f1",
    )
    assert len(decisions) == 1
    assert decisions[0].operation == OperationType.NO_CHANGE
    assert decisions[0].match is not None
    assert decisions[0].match.level in {MatchLevel.L1, MatchLevel.L2, MatchLevel.L3, MatchLevel.L4}
    assert decisions[0].posting_type == "AR"


def test_update_when_change_request_evidences_amount():
    existing = [
        BillRecord(
            bill_id="b1",
            document_type="Debit Note",
            reference_no="DC-1001",
            issuer="NEPTUNE SHIPPING LIMITED",
            recipient="ACME FREIGHT CONSIGNEE LLC",
            charge_item="Handling Charge",
            charge_item_raw="HANDLING CHARGE",
            amount="100.00",
            currency="USD",
            accounting_entity="NEPTUNE SHIPPING LIMITED",
            posting_type="AR",
        )
    ]
    grounded = _grounded("125.50")
    decisions = decide_for_document(
        grounded,
        existing,
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="f2",
        change_requests=[
            ChangeRequest(
                field="amount",
                new_value="125.50",
                evidence=[EvidenceRef(block_id="b1", quote="HANDLING CHARGE 125.50 USD")],
            )
        ],
    )
    assert len(decisions) == 1
    assert decisions[0].operation == OperationType.UPDATE
    assert any(c.field == "amount" for c in (decisions[0].changes or []))
    assert decisions[0].bill.amount == "125.50"
    assert decisions[0].posting_type == "AR"


def test_update_when_llm_emits_aliased_amount_change_request():
    """Regression: DeepSeek often emits field='HANDLING CHARGE amount' / '125.50 USD'."""
    existing = [
        BillRecord(
            bill_id="b1",
            document_type="Debit Note",
            reference_no="DC-1001",
            issuer="NEPTUNE SHIPPING LIMITED",
            recipient="ACME FREIGHT CONSIGNEE LLC",
            charge_item="Handling Charge",
            charge_item_raw="HANDLING CHARGE",
            amount="100.00",
            currency="USD",
            accounting_entity="NEPTUNE SHIPPING LIMITED",
            posting_type="AR",
        )
    ]
    decisions = decide_for_document(
        _grounded("125.50"),
        existing,
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="f2b",
        change_requests=[
            ChangeRequest(
                field="HANDLING CHARGE amount",
                new_value="125.50 USD",
                evidence=[
                    EvidenceRef(
                        block_id="b1",
                        quote="Please amend the HANDLING CHARGE amount from 100.00 USD to 125.50 USD",
                    )
                ],
            )
        ],
    )
    assert decisions[0].operation == OperationType.UPDATE
    assert decisions[0].bill.amount == "125.50"
    assert decisions[0].matched_bill is not None
    assert decisions[0].matched_bill.amount == "100.00"
    assert any(c.field == "amount" and c.new_value == "125.50" for c in decisions[0].changes)


def test_update_not_blocked_by_new_optional_payment_term_raw():
    """Newly extracted Please-Pay prose must not block evidenced amount UPDATE."""
    existing = [
        BillRecord(
            bill_id="b1",
            document_type="Debit Note",
            reference_no="DC-1001",
            issuer="NEPTUNE SHIPPING LIMITED",
            recipient="ACME FREIGHT CONSIGNEE LLC",
            charge_item="Handling Charge",
            charge_item_raw="HANDLING CHARGE",
            amount="100.00",
            currency="USD",
            accounting_entity="NEPTUNE SHIPPING LIMITED",
            posting_type="AR",
        )
    ]
    grounded = GroundedExtraction(
        result=ExtractionResult(
            document_type=EvidencedValue(value="Debit Note"),
            issuer=EvidencedValue(value="NEPTUNE SHIPPING LIMITED"),
            recipient=EvidencedValue(value="ACME FREIGHT CONSIGNEE LLC"),
            reference_no=EvidencedValue(value="DC-1001"),
            payment_term_raw=EvidencedValue(
                value="Please Pay freight against the master B/L shown below"
            ),
        ),
        actual_charges=[
            ExtractedCharge(
                raw_name="HANDLING CHARGE",
                nature=ChargeNature.ACTUAL,
                amount="125.50",
                currency="USD",
                evidence=[EvidenceRef(block_id="b1", quote="HANDLING CHARGE 125.50 USD")],
            )
        ],
    )
    decisions = decide_for_document(
        grounded,
        existing,
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="f2c",
        change_requests=[
            ChangeRequest(
                field="amount",
                new_value="125.50",
                evidence=[EvidenceRef(block_id="b1", quote="amend amount to 125.50")],
            )
        ],
    )
    assert decisions[0].operation == OperationType.UPDATE
    assert decisions[0].bill.amount == "125.50"
    assert decisions[0].bill.payment_term_raw is None


def test_pending_when_amount_differs_without_change_evidence():
    existing = [
        BillRecord(
            bill_id="b1",
            document_type="Debit Note",
            reference_no="DC-1001",
            issuer="NEPTUNE SHIPPING LIMITED",
            recipient="ACME FREIGHT CONSIGNEE LLC",
            charge_item="Handling Charge",
            charge_item_raw="HANDLING CHARGE",
            amount="100.00",
            currency="USD",
            accounting_entity="NEPTUNE SHIPPING LIMITED",
            posting_type="AR",
        )
    ]
    decisions = decide_for_document(
        _grounded("125.50"),
        existing,
        accounting_entity="NEPTUNE SHIPPING LIMITED",
        file_sha256="f3",
    )
    assert decisions[0].operation == OperationType.PENDING_REVIEW
    # Proposed incoming amount must be visible for human review (not masked as 100/100).
    assert decisions[0].matched_bill is not None
    assert decisions[0].matched_bill.amount == "100.00"
    assert decisions[0].bill.amount == "125.50"
    assert decisions[0].changes == []
    assert any("proposed amount" in r for r in decisions[0].audit_reasons)
