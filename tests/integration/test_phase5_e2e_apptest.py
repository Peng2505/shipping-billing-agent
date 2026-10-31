"""Phase 5 AppTest E2E: upload a real sample, run pipeline, verify session outputs.

Marked real_llm — requires LLM_API_KEY and --run-real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app.py"
PDF2 = ROOT / "data" / "samples" / "PDF 示例账单2.pdf"


@pytest.mark.real_llm
def test_phase5_dashboard_run_pdf2_produces_decisions_and_json():
    from streamlit.testing.v1 import AppTest

    from billing_agent.config import load_settings

    if not PDF2.exists():
        pytest.skip("sample PDF2 missing")
    if not load_settings().llm.configured:
        pytest.skip("BLOCKED: LLM not configured")

    at = AppTest.from_file(str(APP), default_timeout=240)
    at.run()
    assert not at.exception, at.exception

    uploaders = at.get("file_uploader")
    assert len(uploaders) >= 1
    uploaders[0].set_value([(PDF2.name, PDF2.read_bytes(), "application/pdf")])
    at.run()
    assert not at.exception, at.exception

    buttons = [b for b in at.button if "开始" in str(b.label)]
    assert buttons, "start button not found"
    buttons[0].click().run(timeout=240)
    assert not at.exception, at.exception

    result = at.session_state.get("pipeline_result")
    assert result is not None, "pipeline_result missing after run"
    assert len(result.all_decisions) >= 3, result.count_ops()
    assert result.delivery_json, "delivery JSON empty"
    amounts = sorted(
        str(d.bill.amount).replace(",", "") for d in result.all_decisions if d.bill.amount
    )
    assert any(a.startswith("65") for a in amounts)
    assert any("1310.40" in a or a.startswith("1310") for a in amounts)
    assert any(a.startswith("35") for a in amounts)
    # Honesty: text layer may be present; OCR API blocks are not required for this test
    for rec in result.delivery_json:
        assert set(rec.keys()) >= {
            "operation",
            "document_info",
            "transaction_party",
            "charge_details",
            "financial_attributes",
            "audit_trail",
        }
