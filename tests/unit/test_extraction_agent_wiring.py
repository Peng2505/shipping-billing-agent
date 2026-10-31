"""ExtractionAgent wiring tests without a real LLM network call."""

import pytest

from billing_agent.agents.extraction_agent import ExtractionAgent, ExtractionAgentError
from billing_agent.agents.document_index import DocumentIndex
from billing_agent.config import LlmSettings
from billing_agent.parsers import ParseContext, parse_path
from billing_agent.schemas import (
    ChargeNature,
    EvidenceRef,
    ExtractedCharge,
    ExtractionResult,
)
from billing_agent.services.llm_factory import LlmCapabilities, LlmNotConfiguredError
from conftest import find_sample


class _FakeAgent:
    def __init__(self, payload: ExtractionResult):
        self.payload = payload
        self.last_context = None

    def invoke(self, inputs, context=None):
        self.last_context = context
        # Simulate the model using tools by calling them through the provided context
        from billing_agent.agents.tools import search_document, verify_evidence

        class RT:
            def __init__(self, ctx):
                self.context = ctx

        rt = RT(context)
        search_document.func(query="HANDLING CHARGE", runtime=rt, limit=3)
        block_id = context.index.block_order[0]
        verify_evidence.func(block_id=block_id, quote="DEBIT", runtime=rt)
        return {"structured_response": self.payload, "messages": []}


def test_not_configured_raises():
    agent = ExtractionAgent(LlmSettings())
    with pytest.raises(LlmNotConfiguredError):
        agent.extract(parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext()))


def test_agent_runs_grounding_and_records_tool_trace():
    doc = parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext())
    index = DocumentIndex.from_document(doc)
    table_id = next(
        bid for bid, b in index.blocks.items()
        if b.table and any("HANDLING CHARGE" in (row[0] or "") for row in (b.table or [])[1:])
    )
    payload = ExtractionResult(
        charges=[
            ExtractedCharge(
                raw_name="HANDLING CHARGE", nature=ChargeNature.ACTUAL,
                amount="65.00", currency="USD",
                evidence=[EvidenceRef(block_id=table_id, quote="HANDLING CHARGE")],
            ),
            ExtractedCharge(
                raw_name="4 ADD'L DETENTION FREE TIME CHARGE", nature=ChargeNature.ACTUAL,
                amount="1310.40", currency="USD",
                evidence=[EvidenceRef(block_id=table_id, quote="4 ADD'L DETENTION FREE TIME CHARGE")],
            ),
            ExtractedCharge(
                raw_name="HANDLING CHARGE", nature=ChargeNature.ACTUAL,
                amount="35.00", currency="USD",
                evidence=[EvidenceRef(block_id=table_id, quote="35.00")],
            ),
        ]
    )
    agent = ExtractionAgent(
        LlmSettings(api_key="x", model="fake"),
        capabilities=LlmCapabilities(True, True, "provider", "fake"),
        model=object(),
        skip_probe=True,
    )
    agent._agent = _FakeAgent(payload)
    agent._strategy_name = "ProviderStrategy"

    grounded = agent.extract(doc)
    assert len(grounded.actual_charges) == 3
    assert grounded.structured_strategy == "ProviderStrategy"
    tools_used = {t["tool"] for t in grounded.tool_trace}
    assert "search_document" in tools_used
    assert "verify_evidence" in tools_used


def test_missing_structured_response_errors():
    class EmptyAgent:
        def invoke(self, inputs, context=None):
            return {"messages": []}

    agent = ExtractionAgent(
        LlmSettings(api_key="x", model="fake"),
        capabilities=LlmCapabilities(True, True, "provider", "fake"),
        model=object(),
        skip_probe=True,
    )
    agent._agent = EmptyAgent()
    agent._strategy_name = "ProviderStrategy"
    with pytest.raises(ExtractionAgentError, match="structured_response"):
        agent.extract(parse_path(find_sample("PDF 示例账单2.pdf"), ParseContext()))
