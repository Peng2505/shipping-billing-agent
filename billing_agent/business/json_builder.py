"""Build the strict 6-block delivery JSON array from Decisions."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from billing_agent.schemas import Decision, OutputRecord, ProcessingResult


def _amount_number(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(Decimal(str(raw).replace(",", "").strip()))
    except InvalidOperation:
        return None


def decision_to_output(decision: Decision) -> OutputRecord:
    bill = decision.bill
    reasons = list(decision.audit_reasons)
    if decision.match and decision.match.reason:
        reasons.append(decision.match.reason)
    if decision.posting_reason:
        reasons.extend(decision.posting_reason)
    for issue in decision.validation_issues:
        reasons.append(f"[{issue.severity}] {issue.code}: {issue.message}")
    # Keep audit short and verifiable
    deduped: list[str] = []
    for r in reasons:
        r = (r or "").strip()
        if r and r not in deduped:
            deduped.append(r)

    return OutputRecord(
        operation=decision.operation.value,
        document_info={
            "document_type": bill.document_type,
            "reference_no": bill.reference_no,
            "document_date": bill.document_date,
        },
        transaction_party={
            "issuer": bill.issuer,
            "recipient": bill.recipient,
        },
        charge_details={
            "charge_item": bill.charge_item,
            "amount": _amount_number(bill.amount),
            "currency": bill.currency,
            "payment_term": bill.payment_term,
        },
        financial_attributes={
            "accounting_entity": bill.accounting_entity,
            "posting_type": decision.posting_type if decision.posting_type is not None else bill.posting_type,
        },
        audit_trail={"ai_reasoning": deduped},
    )


def build_processing_result(decisions: list[Decision]) -> ProcessingResult:
    outputs = [decision_to_output(d) for d in decisions]
    return ProcessingResult(decisions=decisions, output_records=outputs)


def to_delivery_json(result: ProcessingResult) -> list[dict[str, Any]]:
    """Return a JSON-serialisable list matching the assignment schema."""
    payload = [r.model_dump(mode="json") for r in result.output_records]
    # Validate round-trip
    for item in payload:
        OutputRecord.model_validate(item)
    return payload


def dumps_delivery_json(result: ProcessingResult, *, indent: int = 2) -> str:
    return json.dumps(to_delivery_json(result), ensure_ascii=False, indent=indent)


def validate_delivery_json(text: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, [f"invalid JSON: {exc}"]
    if not isinstance(data, list):
        return False, ["top level must be an array"]
    for i, item in enumerate(data):
        try:
            OutputRecord.model_validate(item)
        except ValidationError as exc:
            errors.append(f"record[{i}]: {exc}")
    return (not errors), errors
