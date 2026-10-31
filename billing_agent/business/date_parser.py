"""Parse document dates using in-file evidence only. No geography-based guessing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_YMD_SLASH = re.compile(r"^(\d{4})[./](\d{1,2})[./](\d{1,2})$")
_DMY_OR_MDY = re.compile(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})$")


@dataclass(frozen=True)
class DateParseResult:
    value: date | None
    raw: str | None
    format_used: str | None
    ambiguous: bool
    warning: str | None = None


def _year(y: int) -> int:
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def infer_day_month_order(sibling_raw_dates: list[str]) -> str | None:
    """Return 'DMY', 'MDY', or None from sibling dates in the same file.

    A component > 12 proves that slot is the day.
    """
    dmy_votes = mdy_votes = 0
    for raw in sibling_raw_dates:
        m = _DMY_OR_MDY.match(raw.strip())
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 and b <= 12:
            dmy_votes += 1
        elif b > 12 and a <= 12:
            mdy_votes += 1
    if dmy_votes and not mdy_votes:
        return "DMY"
    if mdy_votes and not dmy_votes:
        return "MDY"
    return None


def parse_document_date(
    raw: str | None,
    *,
    sibling_raw_dates: list[str] | None = None,
) -> DateParseResult:
    if raw is None or not str(raw).strip():
        return DateParseResult(None, raw, None, False)
    text = str(raw).strip()

    m = _ISO.match(text) or _YMD_SLASH.match(text)
    if m:
        value = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return DateParseResult(value, text, "YMD", False, None if value else "invalid_calendar_date")

    m = _DMY_OR_MDY.match(text)
    if not m:
        return DateParseResult(None, text, None, True, "unrecognised_date_format")

    a, b, y = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
    order = infer_day_month_order([*(sibling_raw_dates or []), text])

    if a > 12 and b <= 12:
        value = _safe_date(y, b, a)
        return DateParseResult(value, text, "DMY", False, None if value else "invalid_calendar_date")
    if b > 12 and a <= 12:
        value = _safe_date(y, a, b)
        return DateParseResult(value, text, "MDY", False, None if value else "invalid_calendar_date")

    if order == "DMY":
        value = _safe_date(y, b, a)
        return DateParseResult(value, text, "DMY", False, None if value else "invalid_calendar_date")
    if order == "MDY":
        value = _safe_date(y, a, b)
        return DateParseResult(value, text, "MDY", False, None if value else "invalid_calendar_date")

    return DateParseResult(
        None, text, None, True,
        "DATE_AMBIGUOUS: day/month order not provable from in-file evidence",
    )
