"""Payment-term normalisation. COD / PAY IMMEDIATELY stay as raw (standard=null)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PP = re.compile(r"^(freight\s*)?(pre-?paid|pp|p)$", re.I)
_CC = re.compile(r"^(freight\s*)?(collect|cc|c)$", re.I)


@dataclass(frozen=True)
class PaymentTermResult:
    raw: str | None
    standard: str | None  # PP | CC | None
    notes: str | None = None


def normalize_payment_term(raw: str | None) -> PaymentTermResult:
    if raw is None:
        return PaymentTermResult(None, None)
    text = raw.strip()
    if not text:
        return PaymentTermResult(None, None)
    compact = re.sub(r"\s+", " ", text)
    if _PP.match(compact) or compact.upper() in {"PP", "P", "PREPAID", "FREIGHT PREPAID"}:
        return PaymentTermResult(text, "PP")
    if _CC.match(compact) or compact.upper() in {"CC", "C", "COLLECT", "FREIGHT COLLECT"}:
        return PaymentTermResult(text, "CC")
    # P/C column single letter already handled; remaining are conditions, not PP/CC
    return PaymentTermResult(
        text, None,
        notes="Payment condition retained as raw; not mapped to PP/CC",
    )
