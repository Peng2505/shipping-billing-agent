"""Recover ISO currency from OCR payloads only when explicitly present.

Never treat ``chargeCtr`` as currency (it is a container id field on the
recruiting OCR schema). Never invent USD from the source image when OCR JSON
omits it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from billing_agent.business.currency import ISO_4217, normalize_currency
from billing_agent.schemas import EvidenceRef, EvidencedValue

_AMOUNT_WITH_CCY = re.compile(
    r"(?i)\b([A-Z]{3})\s*([0-9][0-9,]*(?:\.\d+)?)\b|\b([0-9][0-9,]*(?:\.\d+)?)\s*([A-Z]{3})\b"
)
_CURRENCY_KEYS = ("currency", "curr", "ccy", "chargeCurrency", "chargeCurr", "currCode")


def currency_from_ocr_charge_item(item: dict[str, Any]) -> str | None:
    """Return ISO code from an OCR chargeList row when explicitly present."""
    for key in _CURRENCY_KEYS:
        raw = item.get(key)
        if raw in (None, ""):
            continue
        code, _ = normalize_currency(str(raw))
        if code:
            return code
    amount_raw = item.get("amount")
    if isinstance(amount_raw, str):
        m = _AMOUNT_WITH_CCY.search(amount_raw.strip())
        if m:
            code = (m.group(1) or m.group(4) or "").upper()
            if code in ISO_4217:
                return code
    return None


def document_currency_from_ocr_payload(
    payload: dict[str, Any] | str,
    *,
    block_id: str,
) -> EvidencedValue | None:
    """If OCR JSON uniquely names one ISO currency, return it with a quote.

    Empty / missing currency fields (as on ZIM PNG chargeList) → None.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            text = payload
            data = None
    else:
        data = payload
        text = json.dumps(payload, ensure_ascii=False)

    found: dict[str, str] = {}
    if isinstance(data, dict):
        for key in _CURRENCY_KEYS:
            if key in data and data[key] not in (None, ""):
                code, _ = normalize_currency(str(data[key]))
                if code:
                    found[code] = str(data[key])
        for charge in data.get("chargeList") or []:
            if not isinstance(charge, dict):
                continue
            code = currency_from_ocr_charge_item(charge)
            if code:
                quote = next(
                    (
                        str(charge.get(k))
                        for k in _CURRENCY_KEYS
                        if charge.get(k) not in (None, "")
                    ),
                    code,
                )
                found[code] = quote
        # Nested list items (OCR data.list[*])
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            nested = document_currency_from_ocr_payload(item, block_id=block_id)
            if nested and nested.value:
                found[nested.value] = nested.evidence[0].quote if nested.evidence else nested.value

    if len(found) == 1:
        code, quote = next(iter(found.items()))
        return EvidencedValue(
            value=code,
            evidence=[EvidenceRef(block_id=block_id, quote=quote or code)],
        )
    return None


def inherit_currency_onto_charges(
    charges: list,
    doc_currency: EvidencedValue | None,
) -> list:
    """Copy evidenced document-level ISO currency onto charges that lack one."""
    if doc_currency is None or not doc_currency.value:
        return charges
    code, _ = normalize_currency(doc_currency.value)
    if not code:
        return charges
    out = []
    for charge in charges:
        if getattr(charge, "currency", None):
            out.append(charge)
            continue
        note = (getattr(charge, "notes", None) or "").strip()
        extra = f"currency inherited from document-level {code} with evidence"
        notes = f"{note}; {extra}" if note else extra
        out.append(charge.model_copy(update={"currency": code, "notes": notes}))
    return out
