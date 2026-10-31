"""工作台：上传、配置、运行流水线。"""

from __future__ import annotations

import streamlit as st

from billing_agent.business.bill_store import BillStoreError, load_bills_json
from billing_agent.config import load_settings
from billing_agent.pipeline import BillingPipeline, UploadedFile, load_default_synthetic_bills
from billing_agent.schemas import OperationType, SourceOrigin
from billing_agent.ui import labels as L
from billing_agent.ui.formatters import amount_totals_kpi
from billing_agent.ui.state import (
    STATE_ACCOUNTING_ENTITY,
    STATE_ENABLE_OCR_UPLOAD,
    STATE_LAST_ERROR,
    STATE_RUNNING,
    STATE_SETTINGS_STATUS,
    STATE_STAGES,
    STATE_USE_SYNTHETIC_BILLS,
    append_stage,
    clear_run,
    get_result,
    is_demo_mode,
    set_result,
)
from billing_agent.ui.theme import empty_state, kpi_strip, page_header, section_label, service_status_cards


def render() -> None:
    chips = [(L.DEMO_BADGE, "warn")] if is_demo_mode() else []
    page_header(L.DASH_TITLE, L.DASH_CAPTION, chips=chips)

    with st.expander(L.DASH_SECTION_SERVICES, expanded=False):
        status = st.session_state.get(STATE_SETTINGS_STATUS) or {}
        service_status_cards(status)
        if not status.get("llm_configured"):
            st.warning(L.WARN_LLM_BLOCKED, title=L.WARN_LLM_BLOCKED_TITLE)
        if not status.get("storage_configured"):
            st.caption(L.WARN_OSS_BLOCKED)

    left, right = st.columns((1.15, 1), gap="large")
    with left:
        section_label(L.DASH_SECTION_UPLOAD)
        uploads = st.file_uploader(
            L.DASH_UPLOAD_DOCS,
            type=["eml", "pdf", "png", "jpg", "jpeg", "tif", "tiff", "xlsx", "xls", "docx", "doc", "json"],
            accept_multiple_files=True,
            key="dash_uploads",
            help=L.DASH_UPLOAD_DOCS_HELP,
        )
        bills_upload = st.file_uploader(
            L.DASH_UPLOAD_BILLS,
            type=["json"],
            accept_multiple_files=False,
            key="dash_bills",
        )

    with right:
        section_label(L.DASH_SECTION_CONFIG)
        entity = st.text_input(
            L.DASH_ENTITY,
            value=st.session_state.get(STATE_ACCOUNTING_ENTITY) or "",
            key="dash_entity",
            help=L.DASH_ENTITY_HELP,
        )
        st.session_state[STATE_ACCOUNTING_ENTITY] = entity.strip()

        use_synth = st.checkbox(
            L.DASH_SYNTH,
            value=bool(st.session_state.get(STATE_USE_SYNTHETIC_BILLS, True)),
            key="dash_synth",
            help=L.DASH_SYNTH_HELP,
        )
        st.session_state[STATE_USE_SYNTHETIC_BILLS] = use_synth

        enable_ocr = st.checkbox(
            L.DASH_OCR,
            value=bool(st.session_state.get(STATE_ENABLE_OCR_UPLOAD, False)),
            key="dash_ocr",
            help=L.DASH_OCR_HELP,
        )
        st.session_state[STATE_ENABLE_OCR_UPLOAD] = enable_ocr

        c1, c2 = st.columns(2)
        run_clicked = c1.button(L.DASH_START, type="primary", width="stretch", key="dash_run")
        clear_clicked = c2.button(L.DASH_CLEAR, width="stretch", key="dash_clear")

    if clear_clicked:
        clear_run()
        st.rerun()

    if run_clicked:
        if not uploads:
            st.error(L.ERR_MISSING_FILES, title=L.ERR_PIPELINE)
        else:
            _run_pipeline(uploads, bills_upload, entity.strip() or None, use_synth, enable_ocr)

    result = get_result()
    stages = st.session_state.get(STATE_STAGES) or []

    section_label(L.DASH_SECTION_RESULTS)
    if result is None:
        empty_state(L.DASH_EMPTY_SUMMARY_TITLE, L.DASH_EMPTY_SUMMARY)
    else:
        counts = result.count_ops()
        charge_n = sum(len(o.decisions) for o in result.outcomes)
        amt_label, amt_value = amount_totals_kpi(result.all_decisions)
        kpi_strip(
            [
                (L.DASH_METRIC_FILES, len(result.outcomes)),
                (L.DASH_METRIC_CHARGES, charge_n),
                (amt_label, amt_value),
                (L.operation_label(OperationType.CREATE.value), counts.get(OperationType.CREATE.value, 0)),
                (
                    L.operation_label(OperationType.PENDING_REVIEW.value),
                    counts.get(OperationType.PENDING_REVIEW.value, 0),
                ),
            ]
        )
        st.caption(_source_caption(result))

        hard_errors = list(result.errors or [])
        ocr_failed = [w for w in result.warnings if "OCR FAILED" in w or "OCR 失败" in w]
        ocr_skipped = [
            w
            for w in result.warnings
            if "OCR upload disabled" in w or "OCR SKIPPED" in w or "OCR 未执行" in w or "未授权 OCR" in w
        ]
        other_warns = [
            w
            for w in result.warnings
            if w not in ocr_failed and w not in ocr_skipped
        ]

        if hard_errors:
            with st.expander(f"{L.DASH_ERRORS}（{len(hard_errors)}）", expanded=True):
                for e in hard_errors:
                    st.error(L.localize_message(e))
        if ocr_failed:
            st.warning(L.DASH_OCR_FAIL, title=L.DASH_OCR_FAIL_TITLE)
        if other_warns:
            with st.expander(f"{L.DASH_WARNINGS}（{len(other_warns)}）", expanded=False):
                for w in other_warns:
                    st.write(L.localize_message(w))

    with st.expander(L.DASH_STATUS, expanded=False):
        if st.session_state.get(STATE_RUNNING):
            st.status(L.DASH_RUNNING, state="running", expanded=True)
        elif result is not None:
            for ev in stages[-40:]:
                stage = L.stage_label(ev.get("stage"))
                status_label = L.status_label(ev.get("status"))
                extra = L.localize_message(ev.get("note") or ev.get("error") or "")
                st.caption(f"{stage} · {status_label} · {ev.get('file_name', '')} {extra}".strip())
            if result.elapsed_ms is not None:
                st.caption(L.DASH_ELAPSED.format(ms=result.elapsed_ms))
        else:
            st.caption(L.DASH_IDLE)

    if st.session_state.get(STATE_LAST_ERROR):
        st.error(st.session_state[STATE_LAST_ERROR], title=L.ERR_PIPELINE)


def _source_caption(result) -> str:
    has_ocr = False
    has_text = False
    for o in result.outcomes:
        doc = o.document
        if any(b.origin == SourceOrigin.OCR_API for b in doc.blocks):
            has_ocr = True
        if any(b.origin == SourceOrigin.TEXT_LAYER for b in doc.blocks):
            has_text = True
        ocr = doc.ocr
        if ocr and ocr.status.value == "SUCCESS":
            has_ocr = True
    if has_ocr and has_text:
        return L.DASH_SOURCE_MIXED
    if has_ocr:
        return L.DASH_SOURCE_OCR
    if has_text:
        return L.DASH_SOURCE_TEXT
    return ""


def _run_pipeline(uploads, bills_upload, accounting_entity, use_synth, enable_ocr) -> None:
    clear_run()
    st.session_state[STATE_RUNNING] = True
    st.session_state[STATE_STAGES] = []

    files = [UploadedFile(name=f.name, data=f.getvalue()) for f in uploads]
    existing = None
    bills_bytes = None
    bills_name = "bills.json"
    try:
        if bills_upload is not None:
            bills_bytes = bills_upload.getvalue()
            bills_name = bills_upload.name
            load_bills_json(bills_bytes, source_name=bills_name)
        elif use_synth:
            existing = load_default_synthetic_bills()
    except BillStoreError as exc:
        st.session_state[STATE_LAST_ERROR] = f"{L.DASH_BILLS_JSON_ERR}: {exc}"
        st.session_state[STATE_RUNNING] = False
        st.error(str(exc), title=L.DASH_BILLS_JSON_ERR)
        return

    def on_stage(stage: str, status: str, event: dict) -> None:
        append_stage(event)

    try:
        pipeline = BillingPipeline(load_settings(), on_stage=on_stage)
        result = pipeline.run(
            files,
            existing_bills=existing,
            existing_bills_bytes=bills_bytes,
            existing_bills_name=bills_name,
            accounting_entity=accounting_entity,
            enable_ocr_upload=enable_ocr,
        )
        set_result(result)
        if result.errors:
            st.session_state[STATE_LAST_ERROR] = "; ".join(result.errors[:3])
    except Exception as exc:
        st.session_state[STATE_LAST_ERROR] = f"{type(exc).__name__}: {exc}"
        st.error(st.session_state[STATE_LAST_ERROR], title=L.ERR_PIPELINE)
    finally:
        st.session_state[STATE_RUNNING] = False
