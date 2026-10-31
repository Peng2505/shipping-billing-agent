"""Streamlit 入口：航运智能账单助手

运行：streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from billing_agent.ui import audit_view, bill_review, dashboard, document_view, json_output
from billing_agent.ui import labels as L
from billing_agent.ui.state import demo_source_labels, get_result, init_state, is_demo_mode
from pathlib import Path

from billing_agent.ui.theme import apply_theme

_LOGO = Path(__file__).resolve().parent / "billing_agent" / "ui" / "assets" / "logo.svg"

st.set_page_config(
    page_title=L.PAGE_TITLE_BROWSER,
    page_icon=":material/local_shipping:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_state()
apply_theme()
if _LOGO.exists():
    st.logo(str(_LOGO), size="large")

with st.sidebar:
    st.markdown(f"**{L.APP_NAME}**")
    if is_demo_mode():
        sidebar_label, _ = demo_source_labels()
        st.caption(sidebar_label)

    result = get_result()
    if result is not None:
        counts = result.count_ops()
        st.caption(
            f"{L.SIDEBAR_DECISIONS} {len(result.all_decisions)} · "
            f"新建 {counts.get('CREATE', 0)} · "
            f"待复核 {counts.get('PENDING_REVIEW', 0)}"
        )
        if result.errors:
            st.error(f"{len(result.errors)} 项错误", title=L.SIDEBAR_ERRORS)
    else:
        st.caption(L.SIDEBAR_NO_RESULT)

pages = [
    st.Page(
        dashboard.render,
        title=L.NAV_DASHBOARD,
        icon=":material/dashboard:",
        default=True,
        url_path="dashboard",
    ),
    st.Page(
        document_view.render,
        title=L.NAV_DOCUMENTS,
        icon=":material/description:",
        url_path="documents",
    ),
    st.Page(
        bill_review.render,
        title=L.NAV_BILLS,
        icon=":material/compare_arrows:",
        url_path="bills",
    ),
    st.Page(
        audit_view.render,
        title=L.NAV_AUDIT,
        icon=":material/policy:",
        url_path="audit",
    ),
    st.Page(
        json_output.render,
        title=L.NAV_JSON,
        icon=":material/data_object:",
        url_path="json",
    ),
]

page = st.navigation(pages, position="sidebar")
page.run()
