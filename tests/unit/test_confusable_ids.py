"""Confusable-ID heuristic must not flag ordinary shipping numbers as OCR failures."""

from billing_agent.business.validator import detect_confusable_ids


def test_plain_reference_with_digits_alone_is_not_flagged():
    # DC-108478 has 0/1/8 but not both O and 0, I and 1, etc.
    assert detect_confusable_ids("DC-108478") == []


def test_mbl_without_paired_confusables_is_not_flagged():
    assert detect_confusable_ids("MAEU275752922") == []


def test_paired_confusable_chars_are_info_only():
    issues = detect_confusable_ids("BO0KING1I")
    assert len(issues) == 1
    assert issues[0].code == "id_confusable_charset"
    assert issues[0].severity == "info"
    assert "ocr_confusable" not in issues[0].code


def test_validate_bill_does_not_flag_normal_pdf2_ids():
    from billing_agent.business.validator import validate_bill_candidate
    from billing_agent.schemas import BillRecord

    bill = BillRecord(
        reference_no="DC-108478",
        bl_no="MAEU275752922",
        charge_item="Handling Charge",
        amount="65.00",
        currency="USD",
        container_nos=["MRSU2571577", "TCLU8619685"],
    )
    codes = {i.code for i in validate_bill_candidate(bill)}
    assert "id_confusable_charset" not in codes
    assert "ocr_confusable_charset" not in codes
