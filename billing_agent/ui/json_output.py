"""结果导出：Schema、摘要、下载。"""

from __future__ import annotations

import json

import streamlit as st

from billing_agent.business.json_builder import dumps_delivery_json, validate_delivery_json
from billing_agent.ui import labels as L
from billing_agent.ui.formatters import amount_display, dash
from billing_agent.ui.state import get_result, is_demo_mode
from billing_agent.ui.theme import empty_state, kpi_strip, page_header, section_label


def render() -> None:
    chips = [(L.DEMO_BADGE, "warn")] if is_demo_mode() else []
    page_header(L.JSON_TITLE, L.JSON_CAPTION, chips=chips)

    result = get_result()
    if result is None:
        empty_state(L.EMPTY_NO_DATA, L.EMPTY_RUN_FIRST)
        return

    if not result.delivery_json:
        empty_state(L.JSON_EMPTY_TITLE, L.JSON_EMPTY)
        if result.errors:
            for e in result.errors:
                st.error(L.localize_message(e))
        return

    text = dumps_delivery_json(result.processing)
    ok, errors = validate_delivery_json(text)
    counts = result.count_ops()
    biz_n = sum(
        1
        for d in result.all_decisions
        for i in (d.validation_issues or [])
        if i.severity in {"error", "warning"}
    )

    section_label("概览")
    kpi_strip(
        [
            ("记录", len(result.delivery_json)),
            ("Schema", "通过" if ok else "失败"),
            ("业务警告", biz_n),
            (L.operation_label("CREATE"), counts.get("CREATE", 0)),
            (L.operation_label("PENDING_REVIEW"), counts.get("PENDING_REVIEW", 0)),
        ]
    )

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            L.JSON_DL_RESULT,
            data=text.encode("utf-8"),
            file_name="result.json",
            mime="application/json",
            type="primary",
            width="stretch",
            key="dl_result",
        )
    with d2:
        report_text = _report_text(result)
        st.download_button(
            L.JSON_DL_REPORT,
            data=report_text.encode("utf-8"),
            file_name="processing_report.json",
            mime="application/json",
            width="stretch",
            key="dl_report",
        )

    if ok:
        st.caption(f"{L.JSON_VALID.format(n=len(result.delivery_json))} · {L.JSON_SCHEMA_NOTE}")
    else:
        st.error(L.JSON_INVALID, title=L.JSON_INVALID_TITLE)
        for err in errors:
            st.write(f"- {err}")

    section_label(L.JSON_BIZ_SUMMARY)
    st.caption(
        f"CREATE {counts.get('CREATE', 0)} · UPDATE {counts.get('UPDATE', 0)} · "
        f"NO_CHANGE {counts.get('NO_CHANGE', 0)} · PENDING {counts.get('PENDING_REVIEW', 0)} · "
        f"含业务警告/错误的决策 {biz_n}"
    )

    labels = []
    for i, item in enumerate(result.delivery_json):
        op = item.get("operation") if isinstance(item, dict) else None
        charge = ""
        amt = ""
        if isinstance(item, dict):
            details = item.get("charge_details") or {}
            charge = details.get("charge_item") or ""
            amt = amount_display(details.get("amount"))
        labels.append(f"{i+1}. {L.operation_label(op)} · {charge} · {amt}")
    pick = st.selectbox("选择记录", labels, key="json_pick")
    idx = labels.index(pick)
    selected = result.delivery_json[idx]

    section_label(L.JSON_RECORD)
    if isinstance(selected, dict):
        info = selected.get("document_info") or {}
        party = selected.get("transaction_party") or {}
        charge = selected.get("charge_details") or {}
        fin = selected.get("financial_attributes") or {}
        st.dataframe(
            [
                {"字段": "operation", "值": dash(selected.get("operation"))},
                {"字段": "document_type", "值": dash(info.get("document_type"))},
                {"字段": "reference_no", "值": dash(info.get("reference_no"))},
                {"字段": "issuer", "值": dash(party.get("issuer"))},
                {"字段": "recipient", "值": dash(party.get("recipient"))},
                {"字段": "charge_item", "值": dash(charge.get("charge_item"))},
                {"字段": "amount", "值": amount_display(charge.get("amount"))},
                {"字段": "currency", "值": dash(charge.get("currency"))},
                {"字段": "payment_term", "值": dash(charge.get("payment_term"))},
                {"字段": "posting_type", "值": dash(fin.get("posting_type"))},
                {"字段": "accounting_entity", "值": dash(fin.get("accounting_entity"))},
            ],
            alt="记录摘要",
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "payment_term 仅输出 PP/CC 标准值；COD 等条件保留在提取原文，不写入标准字段。"
        )

    tabs = st.tabs(["当前记录 JSON", "完整交付 JSON", L.JSON_REPORT])
    with tabs[0]:
        st.json(selected, expanded=True)
    with tabs[1]:
        st.code(text, language="json")
    with tabs[2]:
        st.json(json.loads(_report_text(result)), expanded=False)


def _report_text(result) -> str:
    report = {
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "elapsed_ms": result.elapsed_ms,
        "demo_mode": result.demo_mode,
        "accounting_entity": result.accounting_entity,
        "service_status": result.service_status,
        "counts": result.count_ops(),
        "warnings": result.warnings,
        "errors": result.errors,
        "stages": result.stages,
        "documents": [
            {
                "file_name": o.document.file_name,
                "status": o.document.status.value,
                "ocr_status": o.document.ocr.status.value if o.document.ocr else None,
                "ocr_error_code": o.document.ocr.error_code if o.document.ocr else None,
                "extract_error": o.extract_error,
                "decisions": len(o.decisions),
            }
            for o in result.outcomes
        ],
    }
    return json.dumps(report, ensure_ascii=False, indent=2)
