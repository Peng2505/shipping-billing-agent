"""处理记录与审计。"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from billing_agent.business.charge_normalizer import normalize_charge_name
from billing_agent.schemas import SourceOrigin
from billing_agent.ui import labels as L
from billing_agent.ui.formatters import (
    amount_display,
    group_validation_issues,
    ocr_status_label,
    standard_name_display,
)
from billing_agent.ui.state import get_result, is_demo_mode
from billing_agent.ui.theme import empty_state, kpi_strip, page_header, render_timeline, section_label


def render() -> None:
    chips = [(L.DEMO_BADGE, "warn")] if is_demo_mode() else []
    page_header(L.AUDIT_TITLE, L.AUDIT_CAPTION, chips=chips)

    result = get_result()
    if result is None:
        empty_state(L.EMPTY_NO_DATA, L.EMPTY_RUN_FIRST)
        return

    decisions = result.all_decisions
    counts = result.count_ops()
    ar_n = sum(1 for d in decisions if d.posting_type == "AR")
    ap_n = sum(1 for d in decisions if d.posting_type == "AP")
    biz_warn = sum(
        1
        for d in decisions
        for i in (d.validation_issues or [])
        if i.severity in {"error", "warning"}
    )

    section_label(L.AUDIT_SUMMARY)
    kpi_strip(
        [
            ("文件", len(result.outcomes)),
            ("费用", len(decisions)),
            ("CREATE", counts.get("CREATE", 0)),
            ("AR / AP", f"{ar_n} / {ap_n}"),
            ("业务风险", biz_warn),
        ]
    )
    st.caption(_recognition_summary(result))

    section_label("处理阶段")
    render_timeline(_build_pipeline_steps(result))

    # Core evidence for each decision — compact
    section_label("决策与依据")
    for outcome in result.outcomes:
        for d in outcome.decisions:
            title = (
                f"{L.operation_label(d.operation.value)} · {d.bill.charge_item} · "
                f"{amount_display(d.bill.amount)} {d.bill.currency or ''}"
            )
            with st.expander(title, expanded=False):
                st.caption(L.posting_label(d.posting_type))
                for r in (d.posting_reason or [])[:4]:
                    st.caption(f"· {r}")
                for r in (d.audit_reasons or [])[:4]:
                    st.caption(f"· {r}")
                buckets = group_validation_issues(d.validation_issues or [])
                if buckets["error"] or buckets["warning"]:
                    st.write(L.AUDIT_VALIDATION)
                    for issue in buckets["error"] + buckets["warning"]:
                        st.caption(f"[{issue.severity}] {issue.code}: {issue.message}")

    with st.expander(L.AUDIT_NORM, expanded=False):
        norm_rows = []
        for outcome in result.outcomes:
            if not outcome.grounded:
                continue
            g = outcome.grounded
            for c in list(g.actual_charges) + list(g.excluded_charges):
                n = normalize_charge_name(c.raw_name)
                norm_rows.append(
                    {
                        L.AUDIT_COL_RAW: c.raw_name,
                        L.AUDIT_COL_STD: standard_name_display(n.standard_name, c.raw_name),
                        L.AUDIT_COL_ALIAS: n.matched_alias or "—",
                        L.DOC_COL_NATURE: c.nature.value,
                    }
                )
        st.dataframe(norm_rows or [{L.EMPTY_NO_DATA: "—"}], alt="费用标准化", width="stretch")

    with st.expander(L.AUDIT_TECH, expanded=False):
        section_label(L.AUDIT_TIMELINE)
        if result.stages:
            st.dataframe(
                [
                    {
                        L.AUDIT_COL_AT: _fmt_time(s.get("at")),
                        L.AUDIT_COL_STAGE: L.stage_label(s.get("stage")),
                        L.AUDIT_COL_STATUS: L.status_label(s.get("status")),
                        L.AUDIT_COL_FILE: s.get("file_name") or "—",
                        L.AUDIT_COL_DETAIL: L.localize_message(
                            s.get("note") or s.get("error") or s.get("model") or ""
                        ),
                    }
                    for s in result.stages
                ],
                alt="时间线",
                width="stretch",
            )
        else:
            st.caption(L.AUDIT_NO_STAGES)

        with st.expander(L.AUDIT_SVC, expanded=False):
            st.json(result.service_status, expanded=False)

        for outcome in result.outcomes:
            if outcome.grounded and outcome.grounded.tool_trace:
                with st.expander(f"{L.AUDIT_TOOLS} · {outcome.document.file_name}", expanded=False):
                    summary = []
                    for item in outcome.grounded.tool_trace[:50]:
                        if isinstance(item, dict):
                            summary.append(
                                {
                                    "tool": item.get("name") or item.get("tool"),
                                    "keys": list(
                                        (item.get("args") or item.get("arguments") or {}).keys()
                                    )
                                    if isinstance(item.get("args") or item.get("arguments"), dict)
                                    else None,
                                }
                            )
                    st.json(summary, expanded=False)

    hard_warns = [
        w
        for w in (result.warnings or [])
        if "OCR FAILED" in w or "OCR 失败" in w or "FAILED" in w
    ]
    if hard_warns:
        section_label(L.AUDIT_WARNINGS)
        for w in hard_warns:
            st.warning(L.localize_message(w))
    if result.errors:
        section_label(L.AUDIT_ERRORS)
        for e in result.errors:
            st.error(L.localize_message(e))


def _fmt_time(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw


def _recognition_summary(result) -> str:
    """Summarise evidence sources for root docs and nested attachments.

    EML body blocks use origin=native (not text_layer). Counting only
    text_layer previously mis-labelled emails as「无可用文本」.
    """
    parts = []
    for o in result.outcomes:
        doc = o.document
        for node in doc.iter_documents():
            ocr = node.ocr
            native_n = len(node.blocks_by_origin(SourceOrigin.NATIVE))
            text_n = len(node.blocks_by_origin(SourceOrigin.TEXT_LAYER))
            ocr_n = len(node.blocks_by_origin(SourceOrigin.OCR_API))
            label = node.file_name
            if node is not doc:
                label = f"{doc.file_name} > {node.file_name}"
            if ocr and ocr.status.value == "SUCCESS":
                parts.append(f"{label}：OCR 已识别（{ocr_n} 块）")
            elif text_n:
                ocr_zh = ocr_status_label(
                    ocr.status.value if ocr else None,
                    ocr.error_code if ocr else None,
                )
                parts.append(f"{label}：PDF 文本层（{text_n} 块）· {ocr_zh}")
            elif native_n:
                kind = "邮件原文" if node.detected_type.value == "eml" else "原文"
                parts.append(f"{label}：{kind}（{native_n} 块）")
            elif node.children:
                parts.append(f"{label}：无正文块 · 附件 {len(node.children)} 个")
            else:
                parts.append(f"{label}：无可用文本")
        if doc.children and not any(
            p.startswith(f"{doc.file_name} >") for p in parts
        ):
            # Root already summarised; ensure attachment count is visible once.
            parts.append(f"{doc.file_name}：附件 {len(doc.children)} 个")
    return " · ".join(parts)


def _stage_bucket(result) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for s in result.stages or []:
        buckets.setdefault(str(s.get("stage") or ""), []).append(s)
    return buckets


def _status_from_events(events: list[dict], *, empty: str = "skip") -> str:
    if not events:
        return empty
    statuses = {e.get("status") for e in events}
    if "failed" in statuses or "blocked" in statuses:
        return "fail"
    if "ok" in statuses or "success" in statuses:
        return "ok"
    if "skipped" in statuses or "empty" in statuses:
        return "skip"
    return "warn"


def _build_pipeline_steps(result) -> list[dict[str, str]]:
    buckets = _stage_bucket(result)
    decisions = result.all_decisions
    grounded = [o for o in result.outcomes if o.grounded is not None]
    extract_errors = [o for o in result.outcomes if o.extract_error]

    ocr_events = buckets.get("ocr", [])
    ocr_success = any(
        o.document.ocr and o.document.ocr.status.value == "SUCCESS" for o in result.outcomes
    )
    ocr_failed = any(
        o.document.ocr and o.document.ocr.status.value == "FAILED" for o in result.outcomes
    )
    ocr_skipped = any(
        o.document.ocr
        and o.document.ocr.status.value in {"NOT_APPLICABLE", "NOT_CONFIGURED"}
        for o in result.outcomes
    ) or any(e.get("status") == "skipped" for e in ocr_events)

    if ocr_success:
        ocr_status, ocr_meta = "ok", "OCR 已执行"
    elif ocr_failed:
        ocr_status, ocr_meta = "fail", "OCR 失败"
    elif ocr_skipped:
        ocr_status, ocr_meta = "skip", "本次未执行 OCR"
    else:
        ocr_status, ocr_meta = "skip", "无 OCR 事件"

    if grounded:
        extract_status, extract_meta = "ok", f"提取 {len(grounded)} 份"
    elif extract_errors:
        extract_status, extract_meta = "fail", f"失败 {len(extract_errors)}"
    else:
        extract_status = _status_from_events(buckets.get("extract", []), empty="skip")
        extract_meta = "无提取"

    issues = [
        d
        for d in decisions
        if any(i.severity in {"error", "warning"} for i in (d.validation_issues or []))
    ]
    if not decisions:
        val_status, val_meta = "skip", "无决策"
    elif issues:
        val_status, val_meta = "warn", f"{len(issues)} 条含业务警告/错误"
    else:
        val_status, val_meta = "ok", "无阻断性问题"

    return [
        {"title": "1. 文档解析", "status": _status_from_events(buckets.get("parse", [])), "meta": f"{len(result.outcomes)} 份"},
        {"title": "2. OCR", "status": ocr_status, "meta": ocr_meta},
        {"title": "3. 字段提取", "status": extract_status, "meta": extract_meta},
        {"title": "4. 费用标准化", "status": "ok" if grounded else "skip", "meta": ""},
        {"title": "5. 账单匹配", "status": "ok" if decisions else "skip", "meta": f"{len(decisions)}"},
        {"title": "6. AR/AP", "status": "ok" if decisions else "skip", "meta": ""},
        {"title": "7. 校验", "status": val_status, "meta": val_meta},
        {"title": "8. JSON", "status": "ok" if result.delivery_json else "skip", "meta": f"{len(result.delivery_json or [])}"},
    ]
