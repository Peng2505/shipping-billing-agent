"""Normalize LLM change_requests onto UPDATE whitelist fields.

Does not invent amounts or invent change intent — only maps field aliases
and cleans clearly composed values (e.g. \"125.50 USD\" → amount \"125.50\").
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from billing_agent.business.bill_updater import UPDATE_WHITELIST
from billing_agent.schemas import ChangeRequest

_AMOUNT_TOKEN = re.compile(
    r"(?i)\b(?:amount|amt|value|sum|total|price|fee|charge\s*amount|金额|数额)\b"
)
_CURRENCY_TOKEN = re.compile(r"(?i)\b(?:currency|curr|ccy|币种|货币)\b")
_PAYMENT_TOKEN = re.compile(r"(?i)\b(?:payment[_\s-]?term|pay[_\s-]?term|freight[_\s-]?term|付款条款|运费条款)\b")
_DATE_TOKEN = re.compile(r"(?i)\b(?:document[_\s-]?date|invoice[_\s-]?date|bill[_\s-]?date|单据日期|发票日期)\b")
_QTY_TOKEN = re.compile(r"(?i)\b(?:quantity|qty|数量)\b")
_UNIT_TOKEN = re.compile(r"(?i)\b(?:unit[_\s-]?price|rate|单价)\b")
_CHARGE_RAW_TOKEN = re.compile(r"(?i)\b(?:charge[_\s-]?item[_\s-]?raw|raw[_\s-]?charge|费用原名|原始费用名)\b")
_CHARGE_TOKEN = re.compile(r"(?i)\b(?:charge[_\s-]?item|charge[_\s-]?name|fee[_\s-]?name|费用名称|费用名)\b")

_DECIMAL = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?")
_ISO_CCY = re.compile(r"\b([A-Z]{3})\b")


def _canon_field(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    key = text.lower().replace("-", "_").replace(" ", "_")
    if key in UPDATE_WHITELIST:
        return key
    # Compact forms like chargeitem / paymentterm
    compact = key.replace("_", "")
    for field in UPDATE_WHITELIST:
        if compact == field.replace("_", ""):
            return field

    if _AMOUNT_TOKEN.search(text) or "金额" in text:
        return "amount"
    if _CURRENCY_TOKEN.search(text) or "币种" in text:
        return "currency"
    if _PAYMENT_TOKEN.search(text):
        return "payment_term"
    if _DATE_TOKEN.search(text):
        return "document_date"
    if _QTY_TOKEN.search(text):
        return "quantity"
    if _UNIT_TOKEN.search(text):
        return "unit_price"
    if _CHARGE_RAW_TOKEN.search(text):
        return "charge_item_raw"
    if _CHARGE_TOKEN.search(text):
        return "charge_item"
    # Phrases like "HANDLING CHARGE amount" / "amend amount to ..."
    if re.search(r"(?i)\bamount\b", text) or text.rstrip().endswith("金额"):
        return "amount"
    return None


def _normalize_amount_value(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _DECIMAL.search(text.replace(" ", ""))
    if not match:
        match = _DECIMAL.search(text)
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        return str(Decimal(token))
    except InvalidOperation:
        return None


def _normalize_currency_value(raw: str) -> str | None:
    text = (raw or "").strip().upper()
    if not text:
        return None
    if len(text) == 3 and text.isalpha():
        return text
    found = _ISO_CCY.search(text)
    return found.group(1) if found else None


def normalize_change_request(req: ChangeRequest) -> ChangeRequest | None:
    """Return a whitelist-aligned ChangeRequest, or None if field cannot be mapped."""
    field = _canon_field(req.field)
    if field is None or field not in UPDATE_WHITELIST:
        return None

    new_value = (req.new_value or "").strip()
    if field == "amount":
        cleaned = _normalize_amount_value(new_value)
        if cleaned is None:
            return None
        new_value = cleaned
    elif field == "currency":
        cleaned = _normalize_currency_value(new_value)
        if cleaned is None:
            return None
        new_value = cleaned
    elif not new_value:
        return None

    return ChangeRequest(field=field, new_value=new_value, evidence=list(req.evidence))


def normalize_change_requests(requests: list[ChangeRequest] | None) -> list[ChangeRequest]:
    """Deduplicate by field (last wins) after alias normalization."""
    by_field: dict[str, ChangeRequest] = {}
    for req in requests or []:
        normalized = normalize_change_request(req)
        if normalized is None:
            continue
        by_field[normalized.field] = normalized
    return list(by_field.values())
