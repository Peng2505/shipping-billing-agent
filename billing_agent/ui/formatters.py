"""Display-only formatters (do not alter pipeline / JSON enums)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def dash(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def amount_display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    text = str(value).replace(",", "").strip()
    try:
        d = Decimal(text)
    except InvalidOperation:
        return str(value)
    q = d.quantize(Decimal("0.01")) if d == d.to_integral_value() or "." in text else d
    try:
        return f"{q:,.2f}"
    except Exception:
        return str(value)


def amount_totals_by_currency(decisions) -> dict[str, Decimal]:
    from collections import defaultdict

    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for d in decisions or []:
        bill = getattr(d, "bill", None)
        if bill is None:
            continue
        raw = getattr(bill, "amount", None)
        if not raw:
            continue
        try:
            amt = Decimal(str(raw).replace(",", "").strip())
        except InvalidOperation:
            continue
        cur = (getattr(bill, "currency", None) or "").strip().upper() or "—"
        totals[cur] += amt
    return dict(totals)


def amount_totals_display(decisions) -> str:
    """Sum amounts by currency for KPI, e.g. '1,410.40 USD' or multi-currency join."""
    totals = amount_totals_by_currency(decisions)
    if not totals:
        return "—"
    # Narrow no-break space keeps amount+currency on one line in KPI cards.
    parts = [f"{amount_display(amt)}\u00a0{cur}" for cur, amt in sorted(totals.items())]
    return " · ".join(parts)


def amount_totals_kpi(decisions) -> tuple[str, str]:
    """Return (label, value) so single-currency KPI can show unit in the label too."""
    totals = amount_totals_by_currency(decisions)
    if not totals:
        return ("金额合计", "—")
    if len(totals) == 1:
        cur, amt = next(iter(sorted(totals.items())))
        return (f"金额合计（{cur}）", amount_display(amt))
    return ("金额合计", amount_totals_display(decisions))


def parse_status_label(status: str | None, *, has_text_layer: bool = False, ocr_status: str | None = None) -> str:
    if not status:
        return "—"
    mapping = {
        "PARSED": "解析完成",
        "PARTIAL": "部分可用",
        "FAILED": "解析失败",
        "UNSUPPORTED": "不支持",
        "SKIPPED": "已跳过",
    }
    base = mapping.get(status, status)
    if status == "PARSED" and ocr_status in {"NOT_APPLICABLE", "OCR_NOT_AUTHORIZED"}:
        return "PDF 文本层解析成功 · 本次未执行 OCR"
    if status == "PARTIAL" and has_text_layer and ocr_status != "SUCCESS":
        return "PDF 文本层可用 · OCR 未完成"
    return base


def ocr_status_label(status: str | None, error_code: str | None = None) -> str:
    """User-facing OCR state; never surface raw codes like OCR_NOT_AUTHORIZED."""
    if not status:
        return "未记录 OCR"
    if status == "SUCCESS":
        return "OCR 已识别"
    if status == "FAILED":
        return "OCR 失败"
    if status == "NOT_APPLICABLE" or error_code == "OCR_NOT_AUTHORIZED":
        return "本次未执行 OCR"
    if status == "NOT_CONFIGURED" or error_code == "STORAGE_NOT_CONFIGURED":
        return "OCR 服务未配置"
    return "OCR 状态未知"


def match_status_label(status: str | None) -> str:
    if not status:
        return "—"
    return {
        "matched": "已匹配",
        "none": "无匹配",
        "ambiguous": "匹配歧义",
    }.get(status, status)


def match_level_label(level: str | None) -> str:
    if not level or level in {"NONE", "None", "none"}:
        return "无匹配"
    return level


def match_summary(match) -> str:
    """Single column: level + status without redundant duplicate columns."""
    if match is None:
        return "无匹配"
    status = getattr(match, "status", None)
    level = getattr(getattr(match, "level", None), "value", None) or getattr(match, "level", None)
    if status == "none" or not level or str(level) in {"NONE", "None", "none"}:
        return "无匹配"
    if status == "ambiguous":
        return f"{level} · 歧义"
    if status == "matched":
        return f"{level} · 已匹配"
    return match_level_label(str(level) if level else None)


def standard_name_display(standard: str | None, raw: str | None = None) -> str:
    if standard:
        return standard
    if raw:
        return "未映射 · 保留原始名称"
    return "—"


def group_validation_issues(issues: list) -> dict[str, list]:
    buckets = {"error": [], "warning": [], "info": []}
    for issue in issues or []:
        sev = getattr(issue, "severity", None) or "warning"
        if sev not in buckets:
            sev = "warning"
        buckets[sev].append(issue)
    return buckets
