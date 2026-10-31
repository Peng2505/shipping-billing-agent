"""XLSX (openpyxl) and XLS (xlrd) parser. One table block per non-empty sheet."""

from __future__ import annotations

import io
from datetime import date, datetime, time
from decimal import Decimal

from billing_agent.schemas import BlockKind, DocType, ParsedDocument, ParseStatus, SourceOrigin

MAX_ROWS = 5000
MAX_COLS = 100


def cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        # repr-based conversion keeps 1310.4 as "1310.4" instead of binary float noise
        text = format(Decimal(repr(value)).normalize(), "f")
        return text
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return " ".join(str(value).split())


def _trim(rows: list[list[str]]) -> list[list[str]]:
    rows = [r for r in rows]
    while rows and not any(rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, c in enumerate(r) if c), default=0) for r in rows), default=0)
    return [r[:width] + [""] * (width - len(r[:width])) for r in rows]


def _add_sheet(doc: ParsedDocument, name: str, rows: list[list[str]], truncated: bool) -> None:
    rows = _trim(rows)
    if not any(any(r) for r in rows):
        return
    doc.add_block(
        BlockKind.SHEET, SourceOrigin.NATIVE, "s",
        "\n".join("\t".join(r) for r in rows),
        table=rows, meta={"sheet": name, "rows": len(rows), "truncated": truncated},
    )
    if truncated:
        doc.warnings.append(f"Sheet '{name}' truncated to {MAX_ROWS} rows x {MAX_COLS} columns.")


def _parse_xlsx(doc: ParsedDocument, data: bytes) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows, truncated = [], False
            for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
                if r_idx >= MAX_ROWS:
                    truncated = True
                    break
                if len(row) > MAX_COLS:
                    truncated = True
                rows.append([cell_to_str(v) for v in row[:MAX_COLS]])
            _add_sheet(doc, ws.title, rows, truncated)
    finally:
        wb.close()


def _parse_xls(doc: ParsedDocument, data: bytes) -> None:
    import xlrd

    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    try:
        for sheet in book.sheets():
            truncated = sheet.nrows > MAX_ROWS or sheet.ncols > MAX_COLS
            rows = []
            for r in range(min(sheet.nrows, MAX_ROWS)):
                row = []
                for c in range(min(sheet.ncols, MAX_COLS)):
                    cell = sheet.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        row.append(cell_to_str(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)))
                    elif cell.ctype == xlrd.XL_CELL_NUMBER:
                        row.append(cell_to_str(float(cell.value)))
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        row.append(cell_to_str(bool(cell.value)))
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        row.append("#ERROR")
                    else:
                        row.append(cell_to_str(cell.value))
                rows.append(row)
            _add_sheet(doc, sheet.name, rows, truncated)
    finally:
        book.release_resources()


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    if doc.detected_type == DocType.XLSX:
        _parse_xlsx(doc, data)
    else:
        _parse_xls(doc, data)
    if not doc.blocks:
        doc.status = ParseStatus.PARTIAL
        doc.warnings.append("Workbook contains no non-empty sheets.")
