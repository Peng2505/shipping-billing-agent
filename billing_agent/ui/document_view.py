"""文档解析：结构、文本、OCR、提取与费用。"""

from __future__ import annotations

import json

import streamlit as st

from billing_agent.schemas import SourceOrigin
from billing_agent.ui import labels as L
from billing_agent.ui.formatters import amount_display, parse_status_label
from billing_agent.ui.state import get_result, is_demo_mode
from billing_agent.ui.theme import empty_state, page_header, section_label

_FIELD_ZH = {
    "document_type": "单据类型",
    "reference_no": "单据号",
    "document_date_raw": "单据日期（原文）",
    "issuer": "签发方",
    "recipient": "接收方",
    "bl_no": "提单号",
    "booking_no": "订舱号",
    "currency": "币种",
    "payment_term_raw": "付款条款（原文）",
    "document_total": "单据合计",
}


def render() -> None:
    chips = [(L.DEMO_BADGE, "warn")] if is_demo_mode() else []
    page_header(L.DOC_TITLE, L.DOC_CAPTION, chips=chips)

    result = get_result()
    if result is None or not result.outcomes:
        empty_state(L.EMPTY_NO_DATA, L.EMPTY_RUN_FIRST)
        return

    nav, main = st.columns((0.9, 2.3), gap="large")
    with nav:
        section_label("文档")
        labels = [o.document.file_name for o in result.outcomes]
        choice = st.radio(L.DOC_SELECT, labels, key="doc_select", label_visibility="collapsed")
        outcome = result.outcomes[labels.index(choice)]

    with main:
        doc = outcome.document
        ocr = doc.ocr
        has_text = bool(doc.blocks_by_origin(SourceOrigin.TEXT_LAYER))
        status_zh = parse_status_label(
            doc.status.value,
            has_text_layer=has_text,
            ocr_status=(ocr.error_code if ocr else None) or (ocr.status.value if ocr else None),
        )
        # Single compact status bar — type / status / blocks (OCR folded into status when skipped)
        st.caption(
            f"{doc.detected_type.value.upper()} · {status_zh} · {len(doc.blocks)} 个内容块"
            + (f" · {len(doc.children)} 个附件" if doc.children else "")
        )

        tabs = st.tabs(["原文", "文本块", "OCR", "字段", "费用"])

        with tabs[0]:
            _render_tree(doc, depth=0)
            if doc.email:
                with st.expander(L.DOC_EMAIL, expanded=False):
                    st.json(
                        {
                            "subject": doc.email.subject,
                            "from": doc.email.sender,
                            "to": doc.email.to,
                            "date": doc.email.date,
                        },
                        expanded=False,
                    )

        with tabs[1]:
            origin_keys = ["all", "native", "text_layer", "ocr_api"]
            origin_filter = st.segmented_control(
                L.DOC_ORIGIN_FILTER,
                options=origin_keys,
                default="all",
                format_func=L.origin_label,
                key="block_origin",
            )
            shown = 0
            for block in doc.blocks:
                if origin_filter and origin_filter != "all" and block.origin.value != origin_filter:
                    continue
                shown += 1
                origin_zh = L.origin_label(block.origin.value)
                with st.expander(f"{block.block_id} · {origin_zh}", expanded=shown <= 2):
                    if block.table:
                        st.dataframe(block.table, alt=f"表格 {block.block_id}", width="stretch")
                    if block.text:
                        st.text(block.text)
            if shown == 0:
                empty_state(L.EMPTY_NO_DATA, "当前来源下无内容块。")

        with tabs[2]:
            ocr_n = len(doc.blocks_by_origin(SourceOrigin.OCR_API))
            if ocr is None:
                st.caption("本文件无 OCR 记录。")
            elif ocr.status.value == "SUCCESS":
                st.caption(f"OCR 已识别 · {ocr_n} 个识别块")
                if ocr.raw_response is not None:
                    with st.expander(L.DOC_OCR_RAW, expanded=False):
                        text = json.dumps(ocr.raw_response, ensure_ascii=False, indent=2)
                        st.code(text[:20000] + ("…" if len(text) > 20000 else ""), language="json")
            elif ocr.status.value == "FAILED":
                st.error(
                    L.localize_message(ocr.error_message) or "OCR 识别失败",
                    title=L.DOC_OCR_ERR,
                )
                with st.expander("技术详情", expanded=False):
                    st.caption(f"status={ocr.status.value} · code={ocr.error_code or '—'}")
            else:
                # NOT_APPLICABLE / NOT_CONFIGURED — status already shown in top bar
                st.caption("本次未执行 OCR，解析内容见「文本块」。")
                with st.expander("技术详情", expanded=False):
                    st.caption(f"status={ocr.status.value} · code={ocr.error_code or '—'}")
                    if ocr.error_message:
                        st.caption(L.localize_message(ocr.error_message))

        with tabs[3]:
            if outcome.extract_error:
                st.error(outcome.extract_error, title=L.DOC_EXTRACT_FAIL)
            elif outcome.grounded is None:
                st.caption(L.DOC_EXTRACT_MISSING_BODY)
            else:
                g = outcome.grounded
                st.caption(
                    L.DOC_EXTRACT_META.format(
                        model=g.model_name,
                        strategy=g.structured_strategy,
                        ms=g.elapsed_ms,
                        tools=len(g.tool_trace),
                    )
                )
                er = g.result
                fields = {
                    "document_type": er.document_type,
                    "reference_no": er.reference_no,
                    "document_date_raw": er.document_date_raw,
                    "issuer": er.issuer,
                    "recipient": er.recipient,
                    "bl_no": er.bl_no,
                    "booking_no": er.booking_no,
                    "currency": er.currency,
                    "payment_term_raw": er.payment_term_raw,
                    "document_total": er.document_total,
                }
                rows = []
                for name, ev in fields.items():
                    if ev is None:
                        continue
                    evidence = "; ".join(f"{e.block_id}: {e.quote[:100]}" for e in ev.evidence)
                    val = ev.value
                    if name == "document_total":
                        val = amount_display(val)
                    rows.append(
                        {
                            L.DOC_COL_FIELD: _FIELD_ZH.get(name, name),
                            L.DOC_COL_VALUE: val,
                            L.DOC_COL_EVIDENCE: evidence,
                        }
                    )
                if rows:
                    st.dataframe(rows, alt="提取字段", width="stretch", height=min(420, 48 + 36 * len(rows)))
                if g.issues:
                    with st.expander(f"{L.DOC_ISSUES}（{len(g.issues)}）"):
                        st.json([i.model_dump() for i in g.issues], expanded=False)

        with tabs[4]:
            if outcome.grounded is None:
                empty_state(L.DOC_EXTRACT_MISSING, L.DOC_EXTRACT_MISSING_BODY)
            else:
                g = outcome.grounded
                charge_rows = [
                    {
                        L.DOC_COL_RAW: c.raw_name,
                        L.DOC_COL_NATURE: c.nature.value,
                        L.DOC_COL_AMOUNT: amount_display(c.amount),
                        L.DOC_COL_CURRENCY: c.currency or "—",
                        L.DOC_COL_SOURCE: "; ".join(e.block_id for e in c.evidence) or "—",
                    }
                    for c in g.actual_charges
                ]
                st.dataframe(charge_rows or [{L.EMPTY_NO_DATA: "—"}], alt="费用明细", width="stretch")
                if g.excluded_charges:
                    with st.expander(f"{L.DOC_EXCLUDED}（{len(g.excluded_charges)}）"):
                        st.dataframe(
                            [
                                {
                                    L.DOC_COL_RAW: c.raw_name,
                                    L.DOC_COL_NATURE: c.nature.value,
                                    L.DOC_COL_AMOUNT: amount_display(c.amount),
                                    "notes": c.notes,
                                }
                                for c in g.excluded_charges
                            ],
                            alt="已排除费用",
                            width="stretch",
                        )


def _render_tree(doc, depth: int) -> None:
    pad = "　" * depth
    st.markdown(
        L.DOC_TREE_LINE.format(
            pad=pad,
            name=doc.file_name,
            dtype=doc.detected_type.value,
            status=doc.status.value,
        )
    )
    for child in doc.children:
        _render_tree(child, depth + 1)
