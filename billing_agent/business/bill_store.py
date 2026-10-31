"""Load and validate existing-bill JSON (real or synthetic)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from billing_agent.business.charge_normalizer import normalize_charge_name
from billing_agent.schemas import BillRecord


class BillStoreError(ValueError):
    pass


def _from_output_shaped(item: dict[str, Any], *, synthetic: bool) -> BillRecord:
    doc = item.get("document_info") or {}
    party = item.get("transaction_party") or {}
    charge = item.get("charge_details") or {}
    fin = item.get("financial_attributes") or {}
    raw_name = charge.get("charge_item_raw") or charge.get("charge_item")
    standard = charge.get("charge_item")
    if raw_name and not standard:
        standard = normalize_charge_name(str(raw_name)).standard_name or raw_name
    amount = charge.get("amount")
    return BillRecord(
        bill_id=item.get("bill_id") or item.get("id"),
        document_type=doc.get("document_type"),
        reference_no=doc.get("reference_no"),
        document_date=doc.get("document_date"),
        issuer=party.get("issuer"),
        recipient=party.get("recipient"),
        bl_no=item.get("bl_no") or doc.get("bl_no"),
        booking_no=item.get("booking_no") or doc.get("booking_no"),
        house_bl_no=item.get("house_bl_no"),
        container_nos=list(item.get("container_nos") or doc.get("container_nos") or []),
        charge_item=standard,
        charge_item_raw=raw_name,
        amount=None if amount is None else str(amount),
        currency=charge.get("currency"),
        payment_term=charge.get("payment_term"),
        payment_term_raw=charge.get("payment_term_raw"),
        quantity=None if charge.get("quantity") is None else str(charge.get("quantity")),
        unit_price=None if charge.get("unit_price") is None else str(charge.get("unit_price")),
        accounting_entity=fin.get("accounting_entity"),
        posting_type=fin.get("posting_type"),
        fingerprint=item.get("fingerprint"),
        synthetic=synthetic or bool(item.get("_synthetic")),
        extra=_extras(item),
    )


def _extras(item: dict[str, Any]) -> dict[str, Any]:
    extra = {k: v for k, v in item.items() if k.startswith("_")}
    if "line_hint" in item:
        extra["line_hint"] = item["line_hint"]
    if "extra_line_hint" in item:
        extra["line_hint"] = item["extra_line_hint"]
    return extra


def _from_flat(item: dict[str, Any], *, synthetic: bool) -> BillRecord:
    raw_name = item.get("charge_item_raw") or item.get("charge_item")
    standard = item.get("charge_item")
    if raw_name and (not standard or standard == raw_name):
        mapped = normalize_charge_name(str(raw_name)).standard_name
        standard = mapped or standard or raw_name
    amount = item.get("amount")
    return BillRecord(
        bill_id=item.get("bill_id") or item.get("id"),
        document_type=item.get("document_type"),
        reference_no=item.get("reference_no"),
        document_date=item.get("document_date"),
        issuer=item.get("issuer"),
        recipient=item.get("recipient"),
        bl_no=item.get("bl_no"),
        booking_no=item.get("booking_no"),
        house_bl_no=item.get("house_bl_no"),
        container_nos=list(item.get("container_nos") or []),
        charge_item=standard,
        charge_item_raw=raw_name,
        amount=None if amount is None else str(amount),
        currency=item.get("currency"),
        payment_term=item.get("payment_term"),
        payment_term_raw=item.get("payment_term_raw"),
        quantity=None if item.get("quantity") is None else str(item.get("quantity")),
        unit_price=None if item.get("unit_price") is None else str(item.get("unit_price")),
        accounting_entity=item.get("accounting_entity"),
        posting_type=item.get("posting_type"),
        fingerprint=item.get("fingerprint"),
        synthetic=synthetic or bool(item.get("_synthetic")),
        extra=_extras(item),
    )


def parse_bill_item(item: dict[str, Any], *, file_synthetic: bool = False) -> BillRecord:
    if not isinstance(item, dict):
        raise BillStoreError("Bill item must be an object")
    synthetic = file_synthetic or bool(item.get("_synthetic"))
    if "charge_details" in item or "document_info" in item:
        bill = _from_output_shaped(item, synthetic=synthetic)
    else:
        bill = _from_flat(item, synthetic=synthetic)
    if not bill.bill_id:
        raise BillStoreError("Each existing bill requires bill_id")
    if not bill.charge_item and not bill.charge_item_raw:
        raise BillStoreError(f"Bill {bill.bill_id} missing charge_item")
    return bill


def load_bills_json(data: bytes | str | list | dict, *, source_name: str = "memory") -> list[BillRecord]:
    if isinstance(data, (bytes, bytearray)):
        obj = json.loads(data.decode("utf-8-sig"))
    elif isinstance(data, str):
        obj = json.loads(data)
    else:
        obj = data

    file_synthetic = False
    items: list
    if isinstance(obj, dict):
        file_synthetic = bool(obj.get("_synthetic"))
        if "bills" in obj and isinstance(obj["bills"], list):
            items = obj["bills"]
        else:
            items = [obj]
    elif isinstance(obj, list):
        items = obj
        file_synthetic = any(isinstance(x, dict) and x.get("_synthetic") for x in items)
    else:
        raise BillStoreError(f"{source_name}: top level must be array or object")

    bills = [parse_bill_item(item, file_synthetic=file_synthetic) for item in items]
    ids = [b.bill_id for b in bills]
    if len(ids) != len(set(ids)):
        raise BillStoreError(f"{source_name}: duplicate bill_id values")
    return bills


def load_bills_path(path: str | Path) -> list[BillRecord]:
    path = Path(path)
    return load_bills_json(path.read_bytes(), source_name=path.name)
