"""Session state keys and shared Streamlit chrome (Chinese UI)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from billing_agent.config import load_settings
from billing_agent.pipeline import PipelineResult, load_default_synthetic_bills, service_status
from billing_agent.ui import labels as L

STATE_RESULT = "pipeline_result"
STATE_STAGES = "pipeline_stages"
STATE_RUNNING = "pipeline_running"
STATE_LAST_ERROR = "pipeline_last_error"
STATE_ACCOUNTING_ENTITY = "accounting_entity"
STATE_USE_SYNTHETIC_BILLS = "use_synthetic_bills"
STATE_ENABLE_OCR_UPLOAD = "enable_ocr_upload"
STATE_REVIEW_NOTES = "review_notes"
STATE_SETTINGS_STATUS = "settings_status"


def init_state() -> None:
    defaults: dict[str, Any] = {
        STATE_RESULT: None,
        STATE_STAGES: [],
        STATE_RUNNING: False,
        STATE_LAST_ERROR: None,
        STATE_ACCOUNTING_ENTITY: "NEPTUNE SHIPPING LIMITED",
        STATE_USE_SYNTHETIC_BILLS: True,
        STATE_ENABLE_OCR_UPLOAD: False,
        STATE_REVIEW_NOTES: {},
        STATE_SETTINGS_STATUS: None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state[STATE_SETTINGS_STATUS] is None:
        st.session_state[STATE_SETTINGS_STATUS] = service_status(load_settings())


def get_result() -> PipelineResult | None:
    return st.session_state.get(STATE_RESULT)


def set_result(result: PipelineResult | None) -> None:
    st.session_state[STATE_RESULT] = result


def append_stage(event: dict[str, Any]) -> None:
    stages = list(st.session_state.get(STATE_STAGES) or [])
    stages.append(event)
    st.session_state[STATE_STAGES] = stages


def clear_run() -> None:
    st.session_state[STATE_RESULT] = None
    st.session_state[STATE_STAGES] = []
    st.session_state[STATE_LAST_ERROR] = None
    st.session_state[STATE_RUNNING] = False


def _config_label(configured: bool) -> str:
    return L.STATUS_CONFIGURED if configured else L.STATUS_NOT_CONFIGURED


def render_service_banner() -> None:
    """Show configuration presence only — not live connectivity verification."""
    status = st.session_state.get(STATE_SETTINGS_STATUS) or service_status(load_settings())
    cols = st.columns(3)
    storage_ok = bool(status.get("storage_configured"))
    active = status.get("active_file_url_provider") or "—"
    cols[0].metric(L.SVC_LLM, _config_label(bool(status.get("llm_configured"))))
    cols[1].metric(L.SVC_STORAGE, _config_label(storage_ok))
    # Endpoint string present ≠ OCR gateway healthy
    ocr_label = L.STATUS_ENDPOINT_ONLY if status.get("ocr_endpoint_set") else L.STATUS_NOT_CONFIGURED
    cols[2].metric(L.SVC_OCR, ocr_label)
    st.caption(
        f"以上状态仅表示本地配置是否齐全；当前 FileUrlProvider=`{active}`。"
        "「仅已配置地址」不等于 OCR 服务已验证可用。"
    )

    if not status.get("llm_configured"):
        st.warning(L.WARN_LLM_BLOCKED, title=L.WARN_LLM_BLOCKED_TITLE)
    if not storage_ok:
        st.warning(L.WARN_OSS_BLOCKED, title=L.WARN_OSS_BLOCKED_TITLE)


def is_demo_mode(result: PipelineResult | None = None) -> bool:
    """Demo badge follows the ledger actually used for the last run.

    After a pipeline run, only `result.demo_mode` matters (True when loaded
    bills carry `_synthetic`, including uploaded exam JSON). The workbench
    checkbox alone must not keep the badge on if the run used uploaded bills.
    """
    result = result if result is not None else get_result()
    if result is not None:
        return bool(result.demo_mode)
    return bool(st.session_state.get(STATE_USE_SYNTHETIC_BILLS))


def demo_source_labels(result: PipelineResult | None = None) -> tuple[str, str]:
    """Return (sidebar_caption, hint) describing where existing bills came from."""
    result = result if result is not None else get_result()
    source = getattr(result, "bills_source", None) if result is not None else None
    name = getattr(result, "bills_source_name", None) if result is not None else None
    if source == "uploaded":
        hint = L.DEMO_HINT_UPLOADED
        if name:
            hint = f"{hint} 文件：{name}"
        return L.DEMO_SIDEBAR_UPLOADED, hint
    if source == "default_synthetic":
        return L.DEMO_SIDEBAR_DEFAULT, L.DEMO_HINT_DEFAULT
    return L.DEMO_SIDEBAR, L.DEMO_HINT_SHORT


def render_demo_badge(result: PipelineResult | None = None, *, compact: bool = False) -> None:
    """Compact demo-mode notice — avoid repeating long banners on every page."""
    if not is_demo_mode(result):
        return
    _, hint = demo_source_labels(result)
    if compact:
        st.caption(f"**{L.DEMO_BADGE}** · {hint}")
    else:
        st.warning(hint, title=L.DEMO_BADGE)


def render_demo_banner(result: PipelineResult | None = None) -> None:
    """Backward-compatible name used by pages; renders compact badge."""
    render_demo_badge(result, compact=True)


def default_synthetic_loaded() -> bool:
    try:
        return bool(load_default_synthetic_bills())
    except Exception:
        return False
