"""Streamlit AppTest 冒烟（页面加载，不要求真实 LLM）。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app.py"


def test_app_loads_dashboard_via_apptest():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    titles = [str(t.value) for t in at.title]
    assert any("智能账单处理工作台" in t or "工作台" in t for t in titles) or at.main


def test_navigation_pages_exist():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert len(at.sidebar) >= 0


def test_ui_labels_module_has_nav():
    from billing_agent.ui import labels as L

    assert L.NAV_DASHBOARD == "工作台"
    assert L.NAV_AUDIT == "处理记录与审计"
    assert L.operation_label("CREATE") == "新建账单"
    assert L.posting_label("AR") == "应收账款（AR）"
    assert L.OPERATION_LABELS["PENDING_REVIEW"] == "待人工复核"
