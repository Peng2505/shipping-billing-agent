"""UPDATE only fields that have explicit evidence of change."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation

from billing_agent.schemas import BillRecord, ChangeRequest, EvidenceRef, FieldChange

# Fields allowed to change on UPDATE
UPDATE_WHITELIST = frozenset({
    "amount", "currency", "payment_term", "payment_term_raw",
    "document_date", "quantity", "unit_price", "charge_item", "charge_item_raw",
})


def _dec(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation:
        return None


def _values_differ(field: str, old: str | None, new: str | None) -> bool:
    if field in {"amount", "quantity", "unit_price"}:
        a, b = _dec(old), _dec(new)
        if a is not None and b is not None:
            return a != b
    if old is None and new is None:
        return False
    if old is None or new is None:
        return True
    return str(old).strip() != str(new).strip()


def unexplained_diff_needs_review(field: str, old: str | None, new: str | None) -> bool:
    """Whether an incoming whitelist diff without ChangeRequest must PENDING.

    Amount/currency always require review when they differ. Other whitelist
    fields only conflict when the existing bill already had a non-empty value;
    newly extracted optional text (e.g. payment_term_raw from a Please Pay
    sentence) must not block an otherwise evidenced UPDATE.
    """
    if new is None or not _values_differ(field, old, new):
        return False
    if field in {"amount", "currency"}:
        return True
    return old is not None and str(old).strip() != ""


def build_update(
    existing: BillRecord,
    incoming: BillRecord,
    *,
    change_requests: list[ChangeRequest] | None = None,
) -> tuple[BillRecord, list[FieldChange], list[str]]:
    """Return (updated_bill, changes, unresolved_notes).

    Unchanged fields keep existing values. Fields without evidence of change
    are not overwritten even if incoming differs.
    """
    updated = deepcopy(existing)
    changes: list[FieldChange] = []
    unresolved: list[str] = []

    evidenced_fields: dict[str, tuple[str | None, list[EvidenceRef]]] = {}
    for req in change_requests or []:
        if req.field in UPDATE_WHITELIST:
            evidenced_fields[req.field] = (req.new_value, list(req.evidence))

    # Implicit evidence: same matched bill, incoming has a concrete new value and
    # the field is in whitelist. Still requires the incoming value to be present.
    # Decision engine decides whether implicit diffs without ChangeRequest are
    # enough for UPDATE vs PENDING_REVIEW; here we only apply evidenced ones
    # plus clear numeric/currency diffs when explicitly allowed by caller via
    # change_requests OR when incoming carries matching evidence list in extra.
    implicit_ok = (incoming.extra or {}).get("allow_implicit_diff") is True

    for field in UPDATE_WHITELIST:
        old_val = getattr(existing, field, None)
        new_val = getattr(incoming, field, None)
        if field in evidenced_fields:
            new_val, evidence = evidenced_fields[field]
        elif implicit_ok and new_val is not None and _values_differ(field, old_val, new_val):
            evidence = list((incoming.extra or {}).get("field_evidence", {}).get(field, []))
            if not evidence:
                unresolved.append(f"{field} differs but has no evidence")
                continue
        else:
            if field not in evidenced_fields and unexplained_diff_needs_review(field, old_val, new_val):
                unresolved.append(f"{field} differs without explicit change evidence")
            continue

        if not _values_differ(field, old_val, None if new_val is None else str(new_val)):
            continue
        setattr(updated, field, None if new_val is None else str(new_val))
        changes.append(FieldChange(
            field=field, old_value=old_val, new_value=getattr(updated, field),
            evidence=evidence if field in evidenced_fields or evidence else [],
        ))

    return updated, changes, unresolved
