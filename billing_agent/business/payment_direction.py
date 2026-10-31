"""Deterministic payment-direction evidence from document text.

Used to support AR/AP without trusting issuer/recipient alone.
Never invents parties: only returns names that literally appear near
payment cues (Remit to / Beneficiary / Please Pay / Consignee).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_COMPANY = re.compile(
    r"\b("
    r"[A-Z0-9][A-Z0-9 &.'\-/()]{2,80}?"
    r"(?:LIMITED|LTD\.?|LLC|INC\.?|INCORPORATED|CORP\.?|CORPORATION|GMBH|PLC|BV|SA|CO\.?)"
    r")\b",
    re.I,
)

_PAY_CUES = (
    "please pay",
    "total charges to be paid",
    "remit to",
    "payable to",
    "beneficiary",
)

_SECTION_STOP = re.compile(
    r"^(SHIPPER|NOTIFY|CONSIGNEE|SECOND NOTIFY|REMIT TO|ARRIVAL|GENERAL NOTICE|"
    r"PLACE OF|POD |VOYAGE|B/L|TYPE|SCAC|RELEASE DATE|PAYMENT RECEIVED)\b",
    re.I,
)


@dataclass(frozen=True)
class PaymentDirectionEvidence:
    payees: list[str] = field(default_factory=list)
    payers: list[str] = field(default_factory=list)
    cues: list[str] = field(default_factory=list)
    strong: bool = False


def _unique(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = re.sub(r"\s+", " ", n).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(re.sub(r"\s+", " ", n).strip())
    return out


_BANKISH = re.compile(r"\b(BANK|ABA|ROUTING|ACH|ACCOUNT NUMBER|ACCT)\b", re.I)
# OCR/layout fragments like "SECURITIES BV" split from "… Securities BV"
_FRAGMENT_PAYEE = re.compile(
    r"^(SECURITIES|HOLDINGS|SERVICES|TRUST)\s+(BV|LLC|LTD\.?|INC\.?)$",
    re.I,
)


def _companies_in(text: str) -> list[str]:
    out = []
    for m in _COMPANY.finditer(text or ""):
        name = m.group(1).strip()
        if _BANKISH.search(name) or _FRAGMENT_PAYEE.match(name):
            continue
        out.append(name)
    return out


def _is_addressy(text: str) -> bool:
    return bool(
        re.search(
            r"\b(WAY|STREET|SUITE|ROAD|AVE\.?|AVENUE|BLVD|DRIVE|FLOOR|"
            r"UNITED STATES|U\.S\.A\.?|\b[A-Z]{2}\b\s+\d{5})\b",
            text or "",
            re.I,
        )
    )


def _remit_address_payees(lines: list[str]) -> list[str]:
    """When PDF layout detaches Remit-to from its address block, recover payee
    as a company-only line followed by street/city lines after the last REMIT TO.
    """
    last_remit = -1
    for i, line in enumerate(lines):
        if "REMIT TO" in line.upper():
            last_remit = i
    if last_remit < 0:
        return []

    found: list[str] = []
    for i in range(last_remit + 1, len(lines)):
        raw = lines[i].strip()
        if not raw:
            continue
        # Skip party-section headers; keep scanning (layout often inserts them).
        if _SECTION_STOP.match(raw):
            continue
        comps = _companies_in(raw)
        if len(comps) != 1:
            continue
        # Prefer a line that is essentially just the company name.
        if re.sub(r"\s+", " ", raw).strip().upper() != comps[0].upper():
            continue
        nxt = " ".join(lines[j].strip() for j in range(i + 1, min(i + 4, len(lines))))
        if _is_addressy(nxt):
            found.append(comps[0])
    return found


def _window_after_label(lines: list[str], label: str, *, span: int = 12) -> list[str]:
    """Collect company-like lines after a section label until a stop header."""
    found: list[str] = []
    label_u = label.upper()
    for i, line in enumerate(lines):
        if label_u not in line.upper():
            continue
        for j in range(i + 1, min(i + 1 + span, len(lines))):
            raw = lines[j].strip()
            if not raw:
                continue
            if _SECTION_STOP.match(raw) and label_u not in raw.upper():
                break
            found.extend(_companies_in(raw))
            # also accept a bare all-caps company line without suffix if long enough
            if (
                not _companies_in(raw)
                and len(raw) >= 8
                and raw.upper() == raw
                and not raw.startswith("*")
                and not re.search(r"\d{3,}", raw)
            ):
                # skip pure address fragments
                if any(tok in raw.upper() for tok in ("STREET", "SUITE", "ROAD", "AVE", "TEL:", "FAX:", "E MAIL", "E_MAIL", "EMAIL")):
                    continue
        # keep scanning for repeated labels (multi-page notices)
    return found


def extract_payment_direction(text: str | None) -> PaymentDirectionEvidence:
    if not text or not text.strip():
        return PaymentDirectionEvidence()

    lower = text.lower()
    cues = [c for c in _PAY_CUES if c in lower]
    lines = text.splitlines()

    payees: list[str] = []
    # Remit-to / beneficiary windows (skip bank wiring noise inside the window)
    for label, span in (("REMIT TO", 25), ("BENEFICIARY", 8)):
        for name in _window_after_label(lines, label, span=span):
            if _BANKISH.search(name) or _FRAGMENT_PAYEE.match(name):
                continue
            payees.append(name)
    for m in re.finditer(r"Beneficiary\s*:?\s*([^\n]+)", text, flags=re.I):
        payees.extend(_companies_in(m.group(1)))
    for m in re.finditer(r"payable to\s+([A-Z][^\n.]{3,80})", text, flags=re.I):
        # Avoid "payable to the rail provider" style prose
        chunk = m.group(1).strip()
        if chunk.lower().startswith(("the ", "a ", "an ")):
            continue
        payees.extend(_companies_in(chunk))
    # Broken PDF text order: Remit-to label then shipper/consignee headers,
    # with the remittance company+address appearing later (e.g. CMA CGM AMERICA LLC).
    if "remit to" in lower:
        payees.extend(_remit_address_payees(lines))

    payers: list[str] = []
    strong = any(c in lower for c in ("please pay", "total charges to be paid", "remit to"))
    if strong:
        # Freight-due notices: consignee / notice addressee is typically the paying party.
        payers.extend(_window_after_label(lines, "CONSIGNEE", span=15))
        # CMA/similar arrival notices print the addressee under GENERAL NOTICE.
        payers.extend(_window_after_label(lines, "GENERAL NOTICE", span=4))

    payees = _unique(payees)
    payers = _unique(payers)
    # Prefer Consignee/Please-Pay payer role over accidental Remit-to overlap.
    payer_keys = {re.sub(r"\s+", " ", p).strip().upper() for p in payers}
    payees = [p for p in payees if re.sub(r"\s+", " ", p).strip().upper() not in payer_keys]

    return PaymentDirectionEvidence(
        payees=payees,
        payers=payers,
        cues=cues,
        strong=bool(strong and (payees or payers)),
    )
