"""Post-process OCR `orderChange` chargeList items.

Preserves every recognisable OCR line with evidence. Does NOT invent currency.
Does NOT drop Tax rows unconditionally. Does NOT drop a line solely because its
amount equals the document total — row labels / context decide nature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from billing_agent.business.charge_normalizer import normalize_charge_name
from billing_agent.business.ocr_currency import currency_from_ocr_charge_item
from billing_agent.schemas import ChargeNature, EvidenceRef, ExtractedCharge

_TAX_NAMES = re.compile(r"^(tax|vat|gst|sales\s*tax|duty)(\s|$)", re.I)
_TOTAL_NAMES = re.compile(
    r"^(grand\s*)?total(\s|$)|amount\s*due|balance\s*due|^subtotal(\s|$)|paid\s*amount",
    re.I,
)


@dataclass
class FilteredOcrCharge:
    charge: ExtractedCharge
    keep_as_line: bool
    reason: str


def _to_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def classify_ocr_charge_item(item: dict[str, Any], *, block_id: str) -> FilteredOcrCharge:
    """Classify one OCR chargeList item from its own label/context only."""
    name = str(item.get("chargeItem") or "").strip()
    amount_raw = item.get("amount")
    amount_str = None if amount_raw in (None, "") else str(amount_raw).strip()
    amount = _to_decimal(amount_str)
    # chargeCtr is a container id on the recruiting OCR schema — never currency.
    currency = currency_from_ocr_charge_item(item)
    quote = f"{name} {amount_str or ''}{(' ' + currency) if currency else ''}".strip()
    evidence = [EvidenceRef(block_id=block_id, quote=quote)] if quote else []
    raw_snapshot = {
        "chargeItem": item.get("chargeItem"),
        "amount": item.get("amount"),
        "chargeCtr": item.get("chargeCtr"),
        "currency": currency,
    }

    if not name:
        charge = ExtractedCharge(
            raw_name="", nature=ChargeNature.INFORMATIONAL, amount=amount_str,
            evidence=evidence, notes=f"OCR chargeItem empty; raw={raw_snapshot}",
        )
        return FilteredOcrCharge(charge, False, "empty_charge_item")

    if _TOTAL_NAMES.search(name):
        charge = ExtractedCharge(
            raw_name=name, nature=ChargeNature.TOTAL, amount=amount_str,
            evidence=evidence,
            notes=f"OCR total/subtotal label; raw={raw_snapshot}",
        )
        return FilteredOcrCharge(charge, False, "total_row_label")

    if amount is None:
        charge = ExtractedCharge(
            raw_name=name, nature=ChargeNature.INFORMATIONAL, amount=amount_str,
            evidence=evidence, notes=f"OCR amount missing/unparseable; raw={raw_snapshot}",
        )
        return FilteredOcrCharge(charge, False, "invalid_amount")

    if amount <= 0 and not _TAX_NAMES.match(name):
        # Zero non-tax lines are informational; zero tax may still be kept as tax=0.
        charge = ExtractedCharge(
            raw_name=name, nature=ChargeNature.INFORMATIONAL, amount=amount_str,
            evidence=evidence, notes=f"OCR non-positive amount; raw={raw_snapshot}",
        )
        return FilteredOcrCharge(charge, False, "non_positive_amount")

    norm = normalize_charge_name(name)
    if norm.context_nature == "waived":
        charge = ExtractedCharge(
            raw_name=name, nature=ChargeNature.WAIVED, amount=amount_str,
            evidence=evidence, notes=norm.notes,
        )
        return FilteredOcrCharge(charge, False, "waived_context")

    if _TAX_NAMES.match(name):
        # Tax is a real line item when present — keep it with nature=TAX.
        # Downstream rules decide whether it posts; we do not drop it here.
        charge = ExtractedCharge(
            raw_name=name, nature=ChargeNature.TAX, amount=amount_str, currency=currency,
            evidence=evidence,
            notes=(
                f"OCR tax-like label; kept as tax line; "
                f"{'currency=' + currency if currency else 'currency unknown'}; raw={raw_snapshot}"
            ),
        )
        return FilteredOcrCharge(charge, True, "tax_line_kept")

    charge = ExtractedCharge(
        raw_name=name,
        nature=ChargeNature.ACTUAL,
        amount=amount_str,
        currency=currency,
        evidence=evidence,
        notes=(
            f"From OCR chargeList; "
            f"{'currency=' + currency if currency else 'currency not provided by OCR API'}; "
            f"raw={raw_snapshot}"
        ),
    )
    return FilteredOcrCharge(charge, True, "candidate_actual")


def filter_ocr_charge_list(
    items: list[dict[str, Any]],
    *,
    block_id: str,
    document_total: Decimal | None = None,
) -> tuple[list[ExtractedCharge], list[ExtractedCharge], list[str]]:
    """Return (kept_lines, excluded_lines, warnings).

    `document_total` is accepted for API compatibility / audit only. Matching a
    line amount to the document total is NOT sufficient to exclude it.
    """
    kept: list[ExtractedCharge] = []
    excluded: list[ExtractedCharge] = []
    warnings: list[str] = []

    if document_total is not None:
        warnings.append(
            f"document_total={document_total} noted for audit; amount equality alone does not exclude lines"
        )

    for item in items:
        if not isinstance(item, dict):
            warnings.append("OCR chargeList entry is not an object; skipped")
            continue
        filtered = classify_ocr_charge_item(item, block_id=block_id)
        if filtered.keep_as_line:
            kept.append(filtered.charge)
        else:
            excluded.append(filtered.charge)
            warnings.append(f"OCR charge '{filtered.charge.raw_name}' excluded: {filtered.reason}")

    return kept, excluded, warnings
