from decimal import Decimal

from billing_agent.business.ocr_charge_filter import classify_ocr_charge_item, filter_ocr_charge_list
from billing_agent.schemas import ChargeNature


def test_tax_item_is_kept_as_tax_line():
    result = classify_ocr_charge_item(
        {"chargeItem": "Tax", "amount": "8.50", "chargeCtr": ""}, block_id="b1",
    )
    assert result.keep_as_line is True
    assert result.charge.nature == ChargeNature.TAX
    assert "raw=" in (result.charge.notes or "")


def test_total_row_label_excluded():
    result = classify_ocr_charge_item(
        {"chargeItem": "Grand Total", "amount": "26.90", "chargeCtr": ""}, block_id="b1",
    )
    assert result.charge.nature == ChargeNature.TOTAL
    assert result.keep_as_line is False


def test_empty_and_invalid_amount():
    empty = classify_ocr_charge_item({"chargeItem": "", "amount": "1"}, block_id="b1")
    assert empty.keep_as_line is False
    missing = classify_ocr_charge_item({"chargeItem": "Fee", "amount": ""}, block_id="b1")
    assert missing.keep_as_line is False


def test_actual_candidate_has_null_currency():
    result = classify_ocr_charge_item(
        {"chargeItem": "WHARFAGE", "amount": "21.90", "chargeCtr": ""}, block_id="b1",
    )
    assert result.keep_as_line is True
    assert result.charge.currency is None


def test_amount_equal_to_total_is_not_auto_excluded():
    """A real charge may equal the document total (single-line invoice)."""
    items = [
        {"chargeItem": "Handling Charge", "amount": "1410.40", "chargeCtr": ""},
    ]
    kept, excluded, warnings = filter_ocr_charge_list(
        items, block_id="ocr1", document_total=Decimal("1410.40"),
    )
    assert len(kept) == 1
    assert kept[0].raw_name == "Handling Charge"
    assert kept[0].nature == ChargeNature.ACTUAL
    assert excluded == []
    assert any("amount equality alone" in w for w in warnings)


def test_total_label_still_excluded_among_detail_lines():
    items = [
        {"chargeItem": "WHARFAGE ADMINISTRATION FEE", "amount": "5.00", "chargeCtr": ""},
        {"chargeItem": "WHARFAGE", "amount": "21.90", "chargeCtr": ""},
        {"chargeItem": "TOTAL", "amount": "26.90", "chargeCtr": ""},
        {"chargeItem": "Tax", "amount": "2.00", "chargeCtr": ""},
    ]
    kept, excluded, warnings = filter_ocr_charge_list(
        items, block_id="ocr1", document_total=Decimal("26.90"),
    )
    names = [c.raw_name for c in kept]
    assert "WHARFAGE ADMINISTRATION FEE" in names
    assert "WHARFAGE" in names
    assert "Tax" in names  # tax kept
    assert any(c.raw_name == "TOTAL" and c.nature == ChargeNature.TOTAL for c in excluded)
    # WHARFAGE 21.90 must NOT be dropped just for not equaling total either
    assert "21.90" in [c.amount for c in kept]
