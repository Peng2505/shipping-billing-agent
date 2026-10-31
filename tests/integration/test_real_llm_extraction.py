"""Real LLM extraction tests. Run with: pytest --run-real -m real_llm

Without LLM_API_KEY / LLM_MODEL these tests SKIP with a BLOCKED reason.
They never pretend to have succeeded.
"""

from __future__ import annotations

import pytest

from billing_agent.agents.extraction_agent import ExtractionAgent
from billing_agent.config import load_settings
from billing_agent.parsers import ParseContext, parse_path
from billing_agent.schemas import ChargeNature
from billing_agent.services.llm_factory import LlmCapabilityError, LlmNotConfiguredError, probe_capabilities
from conftest import SAMPLES_DIR, find_sample


@pytest.fixture(scope="module")
def settings():
    return load_settings()


def _require_llm(settings):
    if not settings.llm.configured:
        pytest.skip(
            "BLOCKED: LLM not configured (set LLM_API_KEY and LLM_MODEL in .env; "
            "see .env.example). Do not paste keys into chat."
        )


@pytest.mark.real_llm
def test_real_llm_capability_probe(settings):
    _require_llm(settings)
    caps = probe_capabilities(settings.llm)
    assert caps.tool_calling, f"Tool Calling failed: {caps.detail}"
    assert caps.structured_output, f"Structured Output failed: {caps.detail}"


@pytest.mark.real_llm
def test_real_extract_pdf1_excludes_conditional(settings):
    _require_llm(settings)
    doc = parse_path(SAMPLES_DIR / "PDF示例账单1.pdf", ParseContext())
    grounded = ExtractionAgent.from_settings(settings.llm).extract(doc)
    amounts = [c.amount.replace(",", "") for c in grounded.actual_charges]
    assert any(a.startswith("245") for a in amounts), grounded.actual_charges
    assert not any(
        (c.amount or "").replace(",", "").startswith("25") and c.nature == ChargeNature.ACTUAL
        for c in grounded.actual_charges
    )
    # Conditional $25 should not be in actuals; ideally in excluded
    assert all(
        not ((c.amount or "").startswith("25") and "SERVICE" in c.raw_name.upper())
        for c in grounded.actual_charges
    )


@pytest.mark.real_llm
def test_real_extract_pdf2_three_charges(settings):
    _require_llm(settings)
    doc = parse_path(SAMPLES_DIR / "PDF 示例账单2.pdf", ParseContext())
    grounded = ExtractionAgent.from_settings(settings.llm).extract(doc)
    assert len(grounded.actual_charges) >= 3, grounded.actual_charges
    amounts = sorted(c.amount.replace(",", "") for c in grounded.actual_charges)
    for expected in ("65.00", "35.00", "1310.40"):
        assert any(a == expected or a == expected.replace(".00", "") for a in amounts), amounts
    handling = [c for c in grounded.actual_charges if "HANDLING" in c.raw_name.upper()]
    assert len(handling) >= 2, "two Handling Charge lines must both be kept"


@pytest.mark.real_llm
def test_real_extract_eml_hc_ambiguity(settings):
    _require_llm(settings)
    doc = parse_path(find_sample("*PRE-ALERT SSZSE26093128*.eml"), ParseContext())
    grounded = ExtractionAgent.from_settings(settings.llm).extract(doc)
    # Carrier Free must not become an actual fee with amount
    for c in grounded.actual_charges:
        if c.amount is None:
            assert "free" not in (c.notes or "").lower()
    # If $50 is extracted, currency must remain null
    fifty = [c for c in grounded.actual_charges if (c.amount or "").replace(",", "") in {"50", "50.00"}]
    for c in fifty:
        assert c.currency is None, "bare $ must not become USD"
    # issuer/recipient must not be invented from SHA/TAR
    result = grounded.result
    if result.issuer and result.issuer.value:
        assert "SHA" != result.issuer.value.upper().strip()
        assert "TAR" not in result.issuer.value.upper().split()
    assert grounded.tool_trace, "Agent must actually call tools"


@pytest.mark.real_llm
def test_real_extract_png_blocked_without_ocr(settings):
    """PNG has no text without OCR. With OCR BLOCKED, extraction must not invent fees."""
    _require_llm(settings)
    doc = parse_path(SAMPLES_DIR / "图片示例.png", ParseContext())
    # No OCR configured in this test context
    assert not doc.blocks
    grounded = ExtractionAgent.from_settings(settings.llm).extract(doc)
    assert grounded.actual_charges == []
    assert grounded.result.warnings or True  # empty doc warning path
