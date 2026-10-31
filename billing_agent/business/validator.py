"""Financial and structural validations for a bill decision candidate."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from billing_agent.business.currency import normalize_currency
from billing_agent.schemas import BillRecord, ExtractedCharge, ValidationIssue

# ISO 6346 owner code letters use a specific value map for check digit.
_ISO6346_MAP = {}
_n = 10
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _n % 11 == 0:
        _n += 1
    _ISO6346_MAP[_ch] = _n
    _n += 1

_CONFUSABLES = {
    "O": "0", "0": "O",
    "I": "1", "1": "I",
    "S": "5", "5": "S",
    "B": "8", "8": "B",
}


def parse_amount(raw: str | None) -> tuple[Decimal | None, ValidationIssue | None]:
    if raw is None or str(raw).strip() == "":
        return None, ValidationIssue(code="AMOUNT_missing", severity="error", message="amount is missing")
    text = str(raw).strip().replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, ValidationIssue(
            code="amount_invalid", severity="error", message=f"amount is not a valid decimal: {raw!r}",
        )
    if value <= 0:
        return value, ValidationIssue(
            code="amount_non_positive", severity="error", message=f"amount must be > 0, got {value}",
        )
    return value, None


def iso6346_check_digit(container: str) -> int | None:
    code = container.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}\d{6}\d", code):
        return None
    total = 0
    for i, ch in enumerate(code[:10]):
        val = _ISO6346_MAP[ch] if ch.isalpha() else int(ch)
        total += val * (2 ** i)
    return total % 11 % 10


def validate_container(container: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    code = container.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}\d{7}", code):
        issues.append(ValidationIssue(
            code="container_format", severity="warning",
            message=f"container {container!r} is not 4 letters + 7 digits",
            path="container_nos",
        ))
        return issues
    expected = iso6346_check_digit(code)
    actual = int(code[10])
    if expected is not None and expected != actual:
        issues.append(ValidationIssue(
            code="container_check_digit", severity="warning",
            message=f"container {code} check digit {actual} != expected {expected} (possible OCR confusion)",
            path="container_nos",
        ))
    return issues


def detect_confusable_ids(*values: str | None) -> list[ValidationIssue]:
    """Non-blocking heuristic: flag IDs that contain BOTH sides of a confusable pair.

    Shipping references often mix letters and digits (e.g. DC-108478). Presence of a
    single digit 0/1/5/8 alone is normal and must not be labelled as an OCR failure.
    Only when both members of a pair appear (O and 0, I and 1, …) is substitution risk
    elevated enough to surface an informational hint — never a blocking error.
    """
    issues = []
    pairs = (("O", "0"), ("I", "1"), ("S", "5"), ("B", "8"))
    for value in values:
        if not value:
            continue
        upper = value.upper()
        if not re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", value):
            continue
        hit = [f"{a}/{b}" for a, b in pairs if a in upper and b in upper]
        if not hit:
            continue
        issues.append(ValidationIssue(
            code="id_confusable_charset",
            severity="info",
            message=(
                f"identifier {value!r} contains both sides of confusable pair(s) "
                f"{', '.join(hit)}; verify manually if source quality is uncertain"
            ),
        ))
    return issues


def validate_bill_candidate(
    bill: BillRecord,
    *,
    document_total: Decimal | None = None,
    sibling_amounts: list[Decimal] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    amount, amount_issue = parse_amount(bill.amount)
    if amount_issue:
        issues.append(amount_issue)

    currency, currency_issue = normalize_currency(bill.currency)
    if currency_issue:
        issues.append(ValidationIssue(
            code=currency_issue, severity="error",
            message=f"currency {bill.currency!r} rejected ({currency_issue})",
            path="currency",
        ))
    elif bill.currency and currency:
        bill.currency = currency

    if not bill.charge_item and not bill.charge_item_raw:
        issues.append(ValidationIssue(
            code="charge_missing", severity="error", message="charge name missing",
        ))

    for c in bill.container_nos:
        issues.extend(validate_container(c))

    # Containers already have ISO 6346 checks; letter/digit pairs like S/5 are normal
    # in owner codes + serials, so confusable heuristic applies only to free-form IDs.
    issues.extend(detect_confusable_ids(bill.bl_no, bill.booking_no, bill.reference_no))

    if document_total is not None and sibling_amounts is not None and sibling_amounts:
        total = sum(sibling_amounts, Decimal("0"))
        if total != document_total:
            issues.append(ValidationIssue(
                code="total_mismatch", severity="warning",
                message=f"line amounts sum {total} != document total {document_total}",
            ))
    return issues


def fingerprint_for(
    *,
    file_sha256: str,
    line_index: int,
    charge_name: str | None,
    amount: str | None,
    currency: str | None,
    reference_no: str | None,
) -> str:
    import hashlib
    from billing_agent.business.charge_normalizer import normalize_charge_key

    key = "|".join([
        file_sha256,
        str(line_index),
        normalize_charge_key(charge_name or ""),
        (amount or "").replace(",", ""),
        (currency or "").upper(),
        (reference_no or "").upper(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
