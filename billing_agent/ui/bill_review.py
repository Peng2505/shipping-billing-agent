"""账单核对：费用、操作、差异。"""

from __future__ import annotations

import streamlit as st

from billing_agent.schemas import OperationType
from billing_agent.ui import labels as L
from billing_agent.ui.formatters import (
    amount_display,
    dash,
    group_validation_issues,
    match_summary,
)
from billing_agent.ui.state import STATE_REVIEW_NOTES, get_result, is_demo_mode
from billing_agent.ui.theme import (
    empty_state,
    kpi_strip,
    page_header,
    render_compare_panels,
    render_create_compare,
    render_operation_badge,
    section_label,
)

_COMPARE_FIELDS = (
    ("reference_no", "单据编号"),
    ("charge_item", "费用名称"),
    ("amount", "金额"),
    ("currency", "币种"),
    ("bill_id", "账单编号"),
    ("bl_no", "提单号"),
    ("issuer", "签发方"),
    ("recipient", "接收方"),
)


def render() -> None:
    chips = [(L.DEMO_BADGE, "warn")] if is_demo_mode() else []
    page_header(L.BILL_TITLE, L.BILL_CAPTION, chips=chips)

    result = get_result()
    if result is None:
        empty_state(L.EMPTY_NO_DATA, L.EMPTY_RUN_FIRST)
        return

    decisions = result.all_decisions
    if not decisions:
        empty_state(L.BILL_EMPTY_DECISIONS_TITLE, L.BILL_EMPTY_DECISIONS)
        if result.errors:
            for e in result.errors:
                st.error(L.localize_message(e))
        return

    counts = result.count_ops()
    ar_n = sum(1 for d in decisions if d.posting_type == "AR")
    ap_n = sum(1 for d in decisions if d.posting_type == "AP")
    kpi_strip(
        [
            ("费用", len(decisions)),
            (L.operation_label("CREATE"), counts.get("CREATE", 0)),
            (L.operation_label("UPDATE"), counts.get("UPDATE", 0)),
            ("AR", ar_n),
            ("AP", ap_n),
        ]
    )

    op_keys = ["ALL"] + [op.value for op in OperationType]
    post_keys = ["ALL", "AR", "AP", "null"]
    f1, f2 = st.columns(2)
    op_filter = f1.segmented_control(
        L.BILL_FILTER_OP,
        options=op_keys,
        default="ALL",
        format_func=L.operation_label,
        key="bill_op",
    )
    post_filter = f2.segmented_control(
        L.BILL_FILTER_POST,
        options=post_keys,
        default="ALL",
        format_func=L.posting_label,
        key="bill_post",
    )

    filtered = []
    rows = []
    for d in decisions:
        if op_filter and op_filter != "ALL" and d.operation.value != op_filter:
            continue
        posting = d.posting_type if d.posting_type is not None else "null"
        if post_filter and post_filter != "ALL" and posting != post_filter:
            continue
        filtered.append(d)
        rows.append(
            {
                L.BILL_COL_OP: L.operation_label(d.operation.value),
                L.BILL_COL_CHARGE: dash(d.bill.charge_item),
                L.BILL_COL_AMOUNT: amount_display(d.bill.amount),
                L.BILL_COL_CURRENCY: dash(d.bill.currency),
                L.BILL_COL_POST: L.posting_label(d.posting_type),
                L.BILL_COL_MATCH: match_summary(d.match),
                L.BILL_COL_BILL_ID: dash(d.matched_bill.bill_id if d.matched_bill else None),
                L.BILL_COL_REF: dash(d.bill.reference_no),
            }
        )

    section_label("费用明细")
    st.dataframe(rows, alt="账单决策表", width="stretch")

    if not filtered:
        empty_state(L.EMPTY_NO_DATA, L.EMPTY_NO_FILTER)
        return

    detail_labels = [
        f"{i+1}. {L.operation_label(d.operation.value)} · {d.bill.charge_item} · "
        f"{amount_display(d.bill.amount)} {d.bill.currency or ''}"
        for i, d in enumerate(filtered)
    ]
    pick = st.selectbox(L.BILL_DETAIL, detail_labels, key="bill_detail")
    decision = filtered[detail_labels.index(pick)]

    render_operation_badge(decision.operation.value)
    st.caption(f"{L.posting_label(decision.posting_type)} · {match_summary(decision.match)}")

    changed_fields = {ch.field for ch in (decision.changes or [])}
    left_bill = decision.matched_bill
    right_bill = decision.bill

    def _fields(bill, highlight: bool) -> list[tuple[str, object, bool]]:
        if bill is None:
            return [(label, "—", False) for _, label in _COMPARE_FIELDS]
        out = []
        for attr, label in _COMPARE_FIELDS:
            val = getattr(bill, attr, None)
            if attr == "amount":
                val = amount_display(val)
            elif val is None or val == "":
                val = "—"
            out.append((label, val, bool(highlight and attr in changed_fields)))
        return out

    section_label(L.BILL_COMPARE)
    right_fields = _fields(right_bill, True)
    right_fields.append(("收付类型", L.posting_label(decision.posting_type), False))
    if left_bill is None and decision.operation.value == "CREATE":
        render_create_compare(L.BILL_NO_EXISTING, L.BILL_PROPOSED, right_fields)
    else:
        left_title = L.BILL_MATCHED if left_bill else L.BILL_INCOMING
        left_fields = _fields(left_bill if left_bill is not None else decision.bill, False)
        render_compare_panels(left_title, left_fields, L.BILL_PROPOSED, right_fields)

    with st.expander(L.BILL_MATCH, expanded=False):
        if decision.match:
            st.write(f"{match_summary(decision.match)} · {decision.match.reason}")
            if decision.match.steps:
                st.json(decision.match.steps, expanded=False)
        else:
            st.caption(L.BILL_NO_MATCH)

    with st.expander(L.BILL_ARAP, expanded=False):
        st.write(L.posting_label(decision.posting_type))
        for r in decision.posting_reason:
            st.caption(r)

    if decision.changes:
        section_label(L.BILL_CHANGES)
        st.dataframe(
            [
                {
                    "字段": ch.field,
                    L.BILL_COL_OLD: dash(ch.old_value),
                    L.BILL_COL_NEW: dash(ch.new_value),
                }
                for ch in decision.changes
            ],
            alt="字段修改",
            width="stretch",
        )

    _render_validation(decision.validation_issues)

    if decision.audit_reasons:
        with st.expander(L.BILL_AUDIT, expanded=False):
            for r in decision.audit_reasons:
                st.caption(r)

    note_key = decision.fingerprint or detail_labels[detail_labels.index(pick)]
    notes = dict(st.session_state.get(STATE_REVIEW_NOTES) or {})
    with st.expander(L.BILL_REVIEW_NOTE, expanded=False):
        note = st.text_area(L.BILL_REVIEW_PLACEHOLDER, value=notes.get(note_key, ""), key=f"note_{note_key}")
        notes[note_key] = note
        st.session_state[STATE_REVIEW_NOTES] = notes


def _render_validation(issues) -> None:
    if not issues:
        return
    buckets = group_validation_issues(issues)
    errors = buckets["error"]
    warnings = buckets["warning"]
    infos = buckets["info"]

    if errors:
        section_label(L.BILL_VALIDATION)
        for issue in errors:
            st.error(f"[{issue.code}] {issue.message}", title="阻断")
    if warnings:
        with st.expander(L.BILL_WARN_SUMMARY.format(n=len(warnings)), expanded=False):
            for issue in warnings:
                st.warning(f"[{issue.code}] {issue.message}")
    if infos:
        with st.expander(L.BILL_HINTS_SUMMARY.format(n=len(infos)), expanded=False):
            for issue in infos:
                st.caption(f"[{issue.code}] {issue.message}")
