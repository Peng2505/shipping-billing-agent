from dataclasses import dataclass

from billing_agent.agents.document_index import DocumentIndex
from billing_agent.agents.grounding import ground_extraction
from billing_agent.agents.tools import (
    ExtractionContext,
    get_block,
    list_blocks,
    lookup_charge_alias,
    search_document,
    verify_evidence,
)
from billing_agent.parsers import ParseContext, parse_path
from billing_agent.schemas import (
    ChargeNature,
    EvidenceRef,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
)
from conftest import find_sample


@dataclass
class _FakeRuntime:
    context: ExtractionContext


def _runtime_for(doc) -> _FakeRuntime:
    index = DocumentIndex.from_document(doc)
    return _FakeRuntime(ExtractionContext(index=index, tool_trace=[]))


def test_tools_search_get_verify_on_pdf2():
    doc = parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext())
    rt = _runtime_for(doc)

    inventory = list_blocks.func(runtime=rt)
    assert "page_text" in inventory

    hits = search_document.func(query="HANDLING CHARGE", runtime=rt, limit=5)
    assert "D0-" in hits or "block_id" in hits

    # pick a real block id from index
    block_id = next(iter(rt.context.index.block_order))
    block_json = get_block.func(block_id=block_id, runtime=rt)
    assert block_id in block_json

    ok = verify_evidence.func(block_id=block_id, quote="DEBIT NOTE", runtime=rt)
    assert '"ok": true' in ok.lower() or '"ok":true' in ok.lower().replace(" ", "")

    bad = verify_evidence.func(block_id=block_id, quote="THIS QUOTE DOES NOT EXIST 99999", runtime=rt)
    assert "quote_not_found" in bad

    alias = lookup_charge_alias.func(raw_name="H/C", runtime=rt)
    assert "Handling Charge" in alias
    assert rt.context.tool_trace  # tools recorded their use


def test_grounding_rejects_bad_evidence_and_currency_symbol():
    doc = parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext())
    index = DocumentIndex.from_document(doc)
    block_id = next(
        bid for bid, b in index.blocks.items() if "HANDLING CHARGE" in b.text and "65.00" in b.text
    )
    raw = ExtractionResult(
        charges=[
            ExtractedCharge(
                raw_name="HANDLING CHARGE",
                nature=ChargeNature.ACTUAL,
                amount="65.00",
                currency="$",
                evidence=[EvidenceRef(block_id=block_id, quote="HANDLING CHARGE")],
            ),
            ExtractedCharge(
                raw_name="FAKE FEE",
                nature=ChargeNature.ACTUAL,
                amount="1.00",
                evidence=[EvidenceRef(block_id=block_id, quote="NOT IN DOCUMENT XYZ")],
            ),
        ],
        currency=EvidencedValue(value="$", evidence=[EvidenceRef(block_id=block_id, quote="USD")]),
    )
    grounded = ground_extraction(raw, index)
    assert len(grounded.actual_charges) == 1
    assert grounded.actual_charges[0].amount == "65.00"
    assert grounded.actual_charges[0].currency is None  # $ stripped
    assert any(i.reason == "quote_not_found" for i in grounded.issues)
    assert any(i.reason == "symbol_not_iso4217" for i in grounded.issues)


def test_grounding_marks_carrier_free_hc_as_waived():
    doc = parse_path(find_sample("*PRE-ALERT SSZSE26093128*.eml"), ParseContext())
    index = DocumentIndex.from_document(doc)
    body_id = next(
        bid for bid, b in index.blocks.items()
        if b.meta.get("content_type") == "text/plain" and "Carrier Free H/C" in b.text
    )
    raw = ExtractionResult(
        charges=[
            ExtractedCharge(
                raw_name="H/C",
                nature=ChargeNature.ACTUAL,
                amount=None,
                evidence=[EvidenceRef(block_id=body_id, quote="Carrier Free H/C")],
            ),
            ExtractedCharge(
                raw_name="H/C",
                nature=ChargeNature.ACTUAL,
                amount="50",
                currency=None,
                evidence=[EvidenceRef(block_id=body_id, quote="SHA pay TAR：H/C $50")],
            ),
        ],
    )
    grounded = ground_extraction(raw, index)
    natures = { (c.amount, c.nature) for c in grounded.actual_charges + grounded.excluded_charges }
    assert ("50", ChargeNature.ACTUAL) in natures or any(
        c.amount == "50" and c.nature == ChargeNature.ACTUAL for c in grounded.actual_charges
    )
    assert any(c.nature == ChargeNature.WAIVED for c in grounded.excluded_charges)


def test_scripted_pdf1_excludes_conditional_fees():
    """Simulates a correct Agent output for PDF1 and verifies grounding keeps only USD 245."""
    doc = parse_path(find_sample("PDF示例账单1.pdf"), ParseContext())
    index = DocumentIndex.from_document(doc)
    page1 = next(bid for bid, b in index.blocks.items() if b.page == 1 and "245.0000" in b.text)
    page_any = next(bid for bid, b in index.blocks.items() if "SERVICE FEE OF $25.00" in b.text)
    raw = ExtractionResult(
        document_type=EvidencedValue(value="Arrival Notice", evidence=[
            EvidenceRef(block_id=page1, quote="GENERAL NOTICE")]),
        bl_no=EvidencedValue(value="CMDUCHN4053601", evidence=[
            EvidenceRef(block_id=page1, quote="CMDUCHN4053601")]),
        charges=[
            ExtractedCharge(
                raw_name="On Carriage Additional - US Em",
                nature=ChargeNature.ACTUAL,
                amount="245.00",
                currency="USD",
                charge_code="OCA17",
                evidence=[EvidenceRef(block_id=page1, quote="On Carriage Additional - US Em")],
            ),
        ],
        excluded=[
            ExtractedCharge(
                raw_name="SERVICE FEE",
                nature=ChargeNature.CONDITIONAL,
                amount="25.00",
                evidence=[EvidenceRef(block_id=page_any, quote="SERVICE FEE OF $25.00")],
            ),
        ],
        document_total=EvidencedValue(value="245.00", evidence=[
            EvidenceRef(block_id=page1, quote="TOTAL CHARGES TO BE PAID")]),
    )
    grounded = ground_extraction(raw, index)
    assert len(grounded.actual_charges) == 1
    assert grounded.actual_charges[0].amount.startswith("245")
    assert any(c.nature == ChargeNature.CONDITIONAL for c in grounded.excluded_charges)


def test_scripted_pdf2_keeps_three_handling_lines():
    doc = parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext())
    index = DocumentIndex.from_document(doc)
    table_id = next(
        bid for bid, b in index.blocks.items()
        if b.table and b.table[0][0] == "DESCRIPTION"
    )
    raw = ExtractionResult(
        reference_no=EvidencedValue(value="DC-108478", evidence=[
            EvidenceRef(block_id=table_id, quote="DC-108478")]),
        charges=[
            ExtractedCharge(raw_name="HANDLING CHARGE", nature=ChargeNature.ACTUAL,
                            amount="65.00", currency="USD", line_hint="1",
                            evidence=[EvidenceRef(block_id=table_id, quote="HANDLING CHARGE")]),
            ExtractedCharge(raw_name="4 ADD'L DETENTION FREE TIME CHARGE", nature=ChargeNature.ACTUAL,
                            amount="1310.40", currency="USD", line_hint="2",
                            evidence=[EvidenceRef(block_id=table_id, quote="4 ADD'L DETENTION FREE TIME CHARGE")]),
            ExtractedCharge(raw_name="HANDLING CHARGE", nature=ChargeNature.ACTUAL,
                            amount="35.00", currency="USD", line_hint="3",
                            evidence=[EvidenceRef(block_id=table_id, quote="35.00")]),
        ],
    )
    grounded = ground_extraction(raw, index)
    assert len(grounded.actual_charges) == 3
    amounts = sorted(c.amount.replace(",", "") for c in grounded.actual_charges)
    assert amounts == ["1310.40", "35.00", "65.00"]
