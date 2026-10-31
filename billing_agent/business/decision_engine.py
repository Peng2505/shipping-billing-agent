"""Deterministic CREATE / UPDATE / NO_CHANGE / PENDING_REVIEW decisions."""

from __future__ import annotations

from decimal import Decimal

from copy import deepcopy

from billing_agent.business.ar_ap_classifier import classify_ar_ap
from billing_agent.business.bill_matcher import BillMatcher
from billing_agent.business.bill_updater import (
    UPDATE_WHITELIST,
    build_update,
    unexplained_diff_needs_review,
    _values_differ,
)
from billing_agent.business.change_request_normalizer import normalize_change_requests
from billing_agent.business.charge_normalizer import normalize_charge_name
from billing_agent.business.currency import normalize_currency
from billing_agent.business.date_parser import parse_document_date
from billing_agent.business.payment_term import normalize_payment_term
from billing_agent.business.validator import fingerprint_for, parse_amount, validate_bill_candidate
from billing_agent.schemas import (
    BillRecord,
    ChangeRequest,
    ChargeNature,
    Decision,
    ExtractedCharge,
    GroundedExtraction,
    OperationType,
    ValidationIssue,
)


def _evidenced_str(field) -> str | None:
    if field is None:
        return None
    return field.value


def _incoming_from_charge(
    charge: ExtractedCharge,
    grounded: GroundedExtraction,
    *,
    accounting_entity: str | None,
    file_sha256: str,
    line_index: int,
    sibling_dates: list[str],
) -> BillRecord:
    result = grounded.result
    norm = normalize_charge_name(charge.raw_name)
    standard = norm.standard_name or charge.raw_name
    currency, _ = normalize_currency(charge.currency) if charge.currency else (None, None)
    if currency is None and charge.currency is None:
        # try document-level currency
        doc_cur = _evidenced_str(result.currency)
        currency, _ = normalize_currency(doc_cur) if doc_cur else (None, None)

    pay = normalize_payment_term(charge.payment_term_raw or _evidenced_str(result.payment_term_raw))
    date_raw = _evidenced_str(result.document_date_raw)
    parsed_date = parse_document_date(date_raw, sibling_raw_dates=sibling_dates)

    containers = [c.value for c in result.container_nos if c.value]
    fp = fingerprint_for(
        file_sha256=file_sha256,
        line_index=line_index,
        charge_name=standard,
        amount=charge.amount,
        currency=currency,
        reference_no=_evidenced_str(result.reference_no),
    )
    return BillRecord(
        document_type=_evidenced_str(result.document_type),
        reference_no=_evidenced_str(result.reference_no),
        document_date=parsed_date.value.isoformat() if parsed_date.value else None,
        issuer=_evidenced_str(result.issuer),
        recipient=_evidenced_str(result.recipient),
        bl_no=_evidenced_str(result.bl_no),
        booking_no=_evidenced_str(result.booking_no),
        house_bl_no=_evidenced_str(result.house_bl_no),
        container_nos=containers,
        charge_item=standard,
        charge_item_raw=charge.raw_name,
        amount=charge.amount,
        currency=currency,
        payment_term=pay.standard,
        payment_term_raw=pay.raw,
        quantity=charge.quantity,
        unit_price=charge.unit_price,
        accounting_entity=accounting_entity,
        fingerprint=fp,
        extra={
            "line_hint": charge.line_hint,
            "date_raw": date_raw,
            "date_ambiguous": parsed_date.ambiguous,
            "date_warning": parsed_date.warning,
            "nature": charge.nature.value,
        },
    )


def _blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]


def decide_for_document(
    grounded: GroundedExtraction,
    existing_bills: list[BillRecord],
    *,
    accounting_entity: str | None,
    file_sha256: str,
    entity_aliases: dict[str, str] | None = None,
    payee_hints: list[str] | None = None,
    payer_hints: list[str] | None = None,
    prefer_payment_hints: bool = False,
    change_requests: list[ChangeRequest] | None = None,
) -> list[Decision]:
    result = grounded.result
    sibling_dates = [d for d in [_evidenced_str(result.document_date_raw)] if d]
    doc_total_raw = _evidenced_str(result.document_total)
    doc_total = parse_amount(doc_total_raw)[0] if doc_total_raw else None

    # Only process kept lines (actual + tax). Excluded stay out of decisions.
    charges = [c for c in grounded.actual_charges if c.nature in {ChargeNature.ACTUAL, ChargeNature.TAX}]
    sibling_amounts = [a for a in (parse_amount(c.amount)[0] for c in charges) if a is not None]

    matcher = BillMatcher()
    seen_fingerprints: set[str] = set()
    decisions: list[Decision] = []

    # Pre-claim existing fingerprints for idempotency against re-CREATE
    existing_fps = {b.fingerprint for b in existing_bills if b.fingerprint}

    for idx, charge in enumerate(charges):
        incoming = _incoming_from_charge(
            charge, grounded,
            accounting_entity=accounting_entity,
            file_sha256=file_sha256,
            line_index=idx,
            sibling_dates=sibling_dates,
        )
        audit: list[str] = []
        issues = validate_bill_candidate(
            incoming, document_total=doc_total, sibling_amounts=sibling_amounts,
        )

        if incoming.extra.get("date_ambiguous"):
            issues.append(ValidationIssue(
                code="DATE_AMBIGUOUS", severity="warning",
                message=incoming.extra.get("date_warning") or "document date ambiguous",
            ))

        if charge.currency is None and incoming.currency is None:
            # bare symbol or OCR missing currency
            if any("$" in (ev.quote or "") for ev in charge.evidence):
                issues.append(ValidationIssue(
                    code="CURRENCY_UNCONFIRMED", severity="error",
                    message="currency symbol present but not convertible to ISO 4217",
                ))
            elif charge.nature == ChargeNature.ACTUAL:
                issues.append(ValidationIssue(
                    code="CURRENCY_MISSING", severity="error",
                    message="currency missing for actual charge",
                ))

        if not incoming.issuer and not incoming.recipient:
            issues.append(ValidationIssue(
                code="PARTY_UNRESOLVED", severity="warning",
                message="issuer/recipient not established from evidence",
            ))

        fp = incoming.fingerprint or ""
        if fp in seen_fingerprints:
            decisions.append(Decision(
                operation=OperationType.PENDING_REVIEW,
                bill=incoming,
                validation_issues=issues,
                audit_reasons=["Duplicate fingerprint within the same run (idempotency)"],
                fingerprint=fp,
            ))
            continue
        seen_fingerprints.add(fp)

        if fp and fp in existing_fps:
            audit.append("Fingerprint already present on an existing bill — suppressing CREATE")

        if _blocking_issues(issues):
            decisions.append(Decision(
                operation=OperationType.PENDING_REVIEW,
                bill=incoming,
                validation_issues=issues,
                audit_reasons=audit + [f"Blocking validation: {i.code}" for i in _blocking_issues(issues)],
                fingerprint=fp,
            ))
            continue

        match = matcher.match(incoming, existing_bills)
        if match.status == "ambiguous":
            decisions.append(Decision(
                operation=OperationType.PENDING_REVIEW,
                bill=incoming,
                match=match,
                validation_issues=issues,
                audit_reasons=audit + [match.reason or "ambiguous match"],
                fingerprint=fp,
            ))
            continue

        if match.status == "none":
            if fp and fp in existing_fps:
                decisions.append(Decision(
                    operation=OperationType.NO_CHANGE,
                    bill=incoming,
                    match=match,
                    validation_issues=issues,
                    audit_reasons=audit + ["Idempotent re-run: fingerprint already exists"],
                    fingerprint=fp,
                ))
                continue
            arap = classify_ar_ap(
                incoming,
                accounting_entity,
                aliases=entity_aliases,
                payee_hints=payee_hints,
                payer_hints=payer_hints,
                prefer_payment_hints=prefer_payment_hints,
            )
            incoming.posting_type = arap.posting_type
            op = OperationType.PENDING_REVIEW if arap.needs_review else OperationType.CREATE
            decisions.append(Decision(
                operation=op,
                bill=incoming,
                match=match,
                posting_type=arap.posting_type,
                posting_reason=arap.reasons,
                validation_issues=issues,
                audit_reasons=audit + (
                    ["CREATE: valid charge with no unique existing match"]
                    if op == OperationType.CREATE
                    else ["CREATE blocked: AR/AP could not be determined reliably"]
                ),
                fingerprint=fp,
            ))
            continue

        # unique match
        existing = next(b for b in existing_bills if b.bill_id == match.bill_id)
        relevant_requests = [
            r for r in normalize_change_requests(change_requests)
            if r.field in UPDATE_WHITELIST
        ]
        # Build evidenced diffs: only apply when ChangeRequest exists OR values equal
        updated, changes, unresolved = build_update(
            existing, incoming, change_requests=relevant_requests,
        )
        # Detect unexplained differences on whitelist fields
        for field in UPDATE_WHITELIST:
            old_v, new_v = getattr(existing, field, None), getattr(incoming, field, None)
            if not any(c.field == field for c in changes) and unexplained_diff_needs_review(
                field, old_v, new_v
            ):
                if f"{field} differs" not in " ".join(unresolved):
                    unresolved.append(f"{field} differs without explicit change evidence")

        arap = classify_ar_ap(
            updated,
            accounting_entity or existing.accounting_entity,
            aliases=entity_aliases,
            payee_hints=payee_hints,
            payer_hints=payer_hints,
            prefer_payment_hints=prefer_payment_hints,
        )
        updated.accounting_entity = accounting_entity or existing.accounting_entity
        updated.posting_type = arap.posting_type

        if unresolved:
            # Keep applied evidenced updates on bill, and surface other incoming
            # diffs so UI / JSON review can see proposed vs matched amounts.
            proposed = deepcopy(updated)
            proposed_notes: list[str] = []
            for field in UPDATE_WHITELIST:
                old_v = getattr(existing, field, None)
                new_v = getattr(incoming, field, None)
                if (
                    new_v is not None
                    and _values_differ(field, old_v, new_v)
                    and not any(c.field == field for c in changes)
                ):
                    setattr(proposed, field, new_v)
                    proposed_notes.append(
                        f"proposed {field}: {old_v} -> {new_v} (not applied)"
                    )
            decisions.append(Decision(
                operation=OperationType.PENDING_REVIEW,
                bill=proposed,
                matched_bill=existing,
                match=match,
                changes=changes,
                posting_type=arap.posting_type,
                posting_reason=arap.reasons,
                validation_issues=issues,
                audit_reasons=audit + unresolved + proposed_notes + [match.reason or ""],
                fingerprint=fp,
            ))
        elif not changes:
            decisions.append(Decision(
                operation=OperationType.NO_CHANGE,
                bill=existing,
                matched_bill=existing,
                match=match,
                posting_type=arap.posting_type if not arap.needs_review else existing.posting_type,
                posting_reason=arap.reasons,
                validation_issues=issues,
                audit_reasons=audit + ["Matched existing bill; no evidenced field changes"],
                fingerprint=fp,
            ))
        elif arap.needs_review:
            decisions.append(Decision(
                operation=OperationType.PENDING_REVIEW,
                bill=updated,
                matched_bill=existing,
                match=match,
                changes=changes,
                posting_type=None,
                posting_reason=arap.reasons,
                validation_issues=issues,
                audit_reasons=audit + ["UPDATE blocked: AR/AP unresolved"],
                fingerprint=fp,
            ))
        else:
            decisions.append(Decision(
                operation=OperationType.UPDATE,
                bill=updated,
                matched_bill=existing,
                match=match,
                changes=changes,
                posting_type=arap.posting_type,
                posting_reason=arap.reasons,
                validation_issues=issues,
                audit_reasons=audit + [
                    f"UPDATE via {match.level.value}",
                    *[f"{c.field}: {c.old_value} -> {c.new_value}" for c in changes],
                    "Fields without modification evidence kept from existing bill",
                ],
                fingerprint=fp,
            ))

    return decisions
