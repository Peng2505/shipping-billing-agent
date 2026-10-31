"""集中式 UI 主题与展示组件（仅展示层，不改业务逻辑）。"""

from __future__ import annotations

import html
from typing import Any, Iterable, Sequence

import streamlit as st

from billing_agent.ui import labels as L

# --- Tokens (mirror docs/DESIGN.md) ---
BRAND = "#142B49"
ACCENT = "#2563EB"
ACCENT_SOFT = "#EFF4FF"
BG = "#F6F8FC"
SURFACE = "#FFFFFF"
INK = "#1F2937"
MUTED = "#64748B"
LINE = "#E2E8F0"
SUCCESS = "#0D9488"
WARNING = "#D97706"
DANGER = "#DC2626"
NEUTRAL = "#64748B"

_OP_STYLE = {
    "CREATE": (SUCCESS, "#ECFDF8", "新建账单"),
    "UPDATE": (ACCENT, ACCENT_SOFT, "更新账单"),
    "NO_CHANGE": (NEUTRAL, "#F1F5F9", "无需修改"),
    "PENDING_REVIEW": (WARNING, "#FFF7ED", "待人工复核"),
}

_CSS = f"""
<style>
:root {{
  --sb-brand: {BRAND};
  --sb-accent: {ACCENT};
  --sb-accent-soft: {ACCENT_SOFT};
  --sb-bg: {BG};
  --sb-surface: {SURFACE};
  --sb-ink: {INK};
  --sb-muted: {MUTED};
  --sb-line: {LINE};
  --sb-success: {SUCCESS};
  --sb-warning: {WARNING};
  --sb-danger: {DANGER};
}}

/* Stable, low-specificity helpers — avoid deep Streamlit private DOM chains */
.sb-page-header {{
  margin: 0 0 1.25rem 0;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--sb-line);
}}
.sb-page-header h1 {{
  margin: 0;
  font-size: 1.375rem;
  line-height: 1.35;
  font-weight: 600;
  color: var(--sb-brand);
  letter-spacing: -0.01em;
}}
.sb-page-header .sb-sub {{
  margin: 0.35rem 0 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--sb-muted);
  max-width: 52rem;
}}
.sb-chip-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.65rem;
}}
.sb-chip {{
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--sb-line);
  background: var(--sb-surface);
  color: var(--sb-muted);
  font-size: 0.75rem;
  line-height: 1.4;
  font-weight: 500;
}}
.sb-chip--brand {{
  border-color: #C7D2E5;
  background: #F3F6FB;
  color: var(--sb-brand);
}}
.sb-chip--warn {{
  border-color: #F5D0A9;
  background: #FFF7ED;
  color: #9A3412;
}}
.sb-chip--ok {{
  border-color: #A7E3D6;
  background: #ECFDF8;
  color: #0F766E;
}}
.sb-chip--danger {{
  border-color: #FECACA;
  background: #FEF2F2;
  color: #B91C1C;
}}

.sb-section-label {{
  margin: 1.35rem 0 0.65rem;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--sb-muted);
  text-transform: none;
}}

.sb-card-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.25rem 0 1rem;
}}
@media (max-width: 900px) {{
  .sb-card-grid {{ grid-template-columns: 1fr; }}
}}
.sb-svc-card {{
  background: var(--sb-surface);
  border: 1px solid var(--sb-line);
  border-radius: 10px;
  padding: 0.85rem 1rem;
  min-height: 5.25rem;
}}
.sb-svc-card .sb-svc-top {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.45rem;
}}
.sb-svc-card .sb-svc-name {{
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--sb-ink);
}}
.sb-svc-card .sb-svc-hint {{
  margin: 0.35rem 0 0;
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--sb-muted);
}}

.sb-kpi-grid {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0.25rem 0 1rem;
}}
@media (max-width: 1100px) {{
  .sb-kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
}}
@media (max-width: 700px) {{
  .sb-kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
.sb-kpi {{
  background: var(--sb-surface);
  border: 1px solid var(--sb-line);
  border-radius: 10px;
  padding: 0.75rem 0.9rem;
}}
.sb-kpi .sb-kpi-label {{
  font-size: 0.75rem;
  color: var(--sb-muted);
  margin: 0 0 0.25rem;
}}
.sb-kpi .sb-kpi-value {{
  margin: 0;
  font-size: 1.25rem;
  line-height: 1.25;
  font-weight: 600;
  color: var(--sb-brand);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}}

.sb-empty {{
  background: var(--sb-surface);
  border: 1px dashed #CBD5E1;
  border-radius: 10px;
  padding: 1.5rem 1.25rem;
  text-align: left;
}}
.sb-empty h3 {{
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--sb-ink);
}}
.sb-empty p {{
  margin: 0;
  font-size: 0.875rem;
  color: var(--sb-muted);
  line-height: 1.55;
}}

.sb-op {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  border: 1px solid;
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.4;
}}
.sb-op code {{
  font-size: 0.7rem;
  font-weight: 500;
  opacity: 0.85;
}}

.sb-compare {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}}
@media (max-width: 900px) {{
  .sb-compare {{ grid-template-columns: 1fr; }}
}}
.sb-panel {{
  background: var(--sb-surface);
  border: 1px solid var(--sb-line);
  border-radius: 10px;
  padding: 0.85rem 1rem;
}}
.sb-panel h4 {{
  margin: 0 0 0.65rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--sb-muted);
}}
.sb-field {{
  display: grid;
  grid-template-columns: 6.5rem 1fr;
  gap: 0.35rem 0.75rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid #F1F5F9;
  font-size: 0.8125rem;
}}
.sb-field:last-child {{ border-bottom: 0; }}
.sb-field .k {{ color: var(--sb-muted); }}
.sb-field .v {{
  color: var(--sb-ink);
  font-variant-numeric: tabular-nums;
  word-break: break-word;
}}
.sb-field.changed .v {{
  background: #FFF7ED;
  border-radius: 4px;
  padding: 0.05rem 0.3rem;
  box-decoration-break: clone;
}}

.sb-timeline {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.25rem 0 0.85rem;
}}
.sb-step {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--sb-surface);
  border: 1px solid var(--sb-line);
  border-radius: 8px;
  padding: 0.4rem 0.65rem;
  max-width: 100%;
}}
.sb-dot {{
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 999px;
  background: #CBD5E1;
  flex-shrink: 0;
}}
.sb-dot.ok {{ background: var(--sb-success); }}
.sb-dot.fail {{ background: var(--sb-danger); }}
.sb-dot.warn {{ background: var(--sb-warning); }}
.sb-dot.skip {{ background: #94A3B8; }}
.sb-step .sb-step-title {{
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--sb-ink);
  white-space: nowrap;
}}
.sb-step .sb-step-meta {{
  display: none;
}}
.sb-amount {{
  font-variant-numeric: tabular-nums;
  text-align: right;
}}
.sb-tag {{
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  border: 1px solid var(--sb-line);
  font-size: 0.75rem;
  color: var(--sb-muted);
  background: #F8FAFC;
}}

.sb-brand-mark {{
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin: 0.15rem 0 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--sb-line);
}}
.sb-brand-mark .mark {{
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 6px;
  background: var(--sb-brand);
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 0.7rem;
  font-weight: 700;
  flex-shrink: 0;
}}
.sb-brand-mark .name {{
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--sb-brand);
  line-height: 1.25;
}}
.sb-brand-mark .en {{
  font-size: 0.7rem;
  color: var(--sb-muted);
  line-height: 1.3;
}}

.sb-note {{
  margin: 0.35rem 0 0.85rem;
  font-size: 0.75rem;
  color: var(--sb-muted);
  line-height: 1.45;
}}
</style>
"""


def apply_theme() -> None:
    """Inject once per session rerun tree via session flag reset each run from app."""
    st.html(_CSS)


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def page_header(
    title: str,
    subtitle: str,
    *,
    chips: Sequence[tuple[str, str]] | None = None,
) -> None:
    """chips: list of (text, variant) where variant in brand|warn|ok|danger|''."""
    chip_html = ""
    if chips:
        parts = []
        for text, variant in chips:
            cls = f"sb-chip sb-chip--{variant}" if variant else "sb-chip"
            parts.append(f'<span class="{cls}">{_esc(text)}</span>')
        chip_html = f'<div class="sb-chip-row">{"".join(parts)}</div>'
    st.html(
        f"""
        <div class="sb-page-header">
          <h1>{_esc(title)}</h1>
          <p class="sb-sub">{_esc(subtitle)}</p>
          {chip_html}
        </div>
        """
    )


def section_label(text: str) -> None:
    st.html(f'<div class="sb-section-label">{_esc(text)}</div>')


def render_brand_sidebar() -> None:
    st.html(
        """
        <div class="sb-brand-mark">
          <div class="mark">SB</div>
          <div>
            <div class="name">航运智能账单助手</div>
            <div class="en">Shipping Billing AI</div>
          </div>
        </div>
        """
    )


def service_status_cards(status: dict[str, Any]) -> None:
    llm_ok = bool(status.get("llm_configured"))
    storage_ok = bool(status.get("storage_configured"))
    active = status.get("active_file_url_provider") or "—"
    ocr_set = bool(status.get("ocr_endpoint_set"))

    cards = [
        (
            L.SVC_LLM,
            L.STATUS_CONFIGURED if llm_ok else L.STATUS_NOT_CONFIGURED,
            "ok" if llm_ok else "danger",
            "API Key / 模型已配置" if llm_ok else "缺少 LLM_API_KEY 或 LLM_MODEL",
        ),
        (
            L.SVC_STORAGE,
            L.STATUS_CONFIGURED if storage_ok else L.STATUS_NOT_CONFIGURED,
            "ok" if storage_ok else "warn",
            f"Provider：{active}" if storage_ok else "未配置 local_tunnel / R2 / OSS",
        ),
        (
            L.SVC_OCR,
            L.STATUS_ENDPOINT_ONLY if ocr_set else L.STATUS_NOT_CONFIGURED,
            "ok" if ocr_set else "danger",
            "Endpoint 已配置" if ocr_set else "未配置 OCR Endpoint",
        ),
    ]
    cells = []
    for name, state, variant, hint in cards:
        cells.append(
            f"""
            <div class="sb-svc-card">
              <div class="sb-svc-top">
                <div class="sb-svc-name">{_esc(name)}</div>
                <span class="sb-chip sb-chip--{variant}">{_esc(state)}</span>
              </div>
              <p class="sb-svc-hint">{_esc(hint)}</p>
            </div>
            """
        )
    st.html(f'<div class="sb-card-grid">{"".join(cells)}</div>')


def kpi_strip(items: Sequence[tuple[str, Any]]) -> None:
    cells = []
    for label, value in items:
        cells.append(
            f"""
            <div class="sb-kpi">
              <p class="sb-kpi-label">{_esc(label)}</p>
              <p class="sb-kpi-value">{_esc(value)}</p>
            </div>
            """
        )
    st.html(f'<div class="sb-kpi-grid">{"".join(cells)}</div>')


def empty_state(title: str, body: str) -> None:
    st.html(
        f"""
        <div class="sb-empty">
          <h3>{_esc(title)}</h3>
          <p>{_esc(body)}</p>
        </div>
        """
    )


def operation_badge_html(op: str | None) -> str:
    key = op or ""
    color, bg, zh = _OP_STYLE.get(key, (NEUTRAL, "#F1F5F9", key or "—"))
    return (
        f'<span class="sb-op" style="color:{color};background:{bg};border-color:{color}33">'
        f"{_esc(zh)} <code>{_esc(key or '—')}</code></span>"
    )


def render_operation_badge(op: str | None) -> None:
    st.html(operation_badge_html(op))


def bill_panel_html(title: str, fields: Iterable[tuple[str, Any, bool]]) -> str:
    rows = []
    for label, value, changed in fields:
        cls = "sb-field changed" if changed else "sb-field"
        display = "—" if value is None or value == "" else value
        rows.append(
            f'<div class="{cls}"><div class="k">{_esc(label)}</div>'
            f'<div class="v">{_esc(display)}</div></div>'
        )
    return (
        f'<div class="sb-panel"><h4>{_esc(title)}</h4>{"".join(rows)}</div>'
    )


def render_compare_panels(
    left_title: str,
    left_fields: Sequence[tuple[str, Any, bool]],
    right_title: str,
    right_fields: Sequence[tuple[str, Any, bool]],
) -> None:
    st.html(
        '<div class="sb-compare">'
        + bill_panel_html(left_title, left_fields)
        + bill_panel_html(right_title, right_fields)
        + "</div>"
    )


def render_create_compare(
    left_message: str,
    right_title: str,
    right_fields: Sequence[tuple[str, Any, bool]],
) -> None:
    """CREATE: left side is a single notice, not a blank field grid."""
    left = (
        f'<div class="sb-panel"><h4>{_esc("已有账单")}</h4>'
        f'<p class="sb-svc-hint" style="margin:0.5rem 0 0">{_esc(left_message)}</p></div>'
    )
    st.html(
        '<div class="sb-compare">'
        + left
        + bill_panel_html(right_title, right_fields)
        + "</div>"
    )


def render_timeline(steps: Sequence[dict[str, str]]) -> None:
    """Compact horizontal stage chips. Full meta available via expanders in page."""
    blocks = []
    for step in steps:
        status = step.get("status") or "idle"
        title = step.get("title") or ""
        # Drop leading "1. " style numbers for denser strip
        if ". " in title[:4]:
            title = title.split(". ", 1)[-1]
        blocks.append(
            f"""
            <div class="sb-step" title="{_esc(step.get("meta") or "")}">
              <div class="sb-dot {_esc(status)}"></div>
              <p class="sb-step-title">{_esc(title)}</p>
            </div>
            """
        )
    st.html(f'<div class="sb-timeline">{"".join(blocks)}</div>')
