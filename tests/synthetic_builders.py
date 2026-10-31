"""Builders for SYNTHETIC test files. None of this is recruiter-provided data."""

from __future__ import annotations

import io
import json
from email.message import EmailMessage

SYNTHETIC_MARK = "SYNTHETIC TEST DATA"


def xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Charges"
    ws.append([SYNTHETIC_MARK])
    ws.append(["Charge", "Qty", "Unit Price", "Amount", "Currency"])
    ws.append(["Doc Fee", 1, 35.5, 35.5, "USD"])
    ws.append(["THC", 2, 655.2, 1310.4, "USD"])
    wb.create_sheet("Empty")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def xls_bytes() -> bytes:
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Charges")
    rows = [
        [SYNTHETIC_MARK],
        ["Charge", "Qty", "Amount", "Currency"],
        ["Trucking Fee", 1, 120.75, "CNY"],
    ]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            ws.write(r, c, value)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def docx_bytes() -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(SYNTHETIC_MARK)
    document.add_paragraph("Debit Note SYN-DN-001")
    table = document.add_table(rows=3, cols=3)
    for r, row in enumerate([["Charge", "Amount", "Currency"], ["Storage Fee", "80.00", "USD"],
                             ["Customs Fee", "45.00", "USD"]]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    document.add_paragraph("Total USD 125.00")
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def pdf_bytes(text: str = f"{SYNTHETIC_MARK}\nInvoice SYN-INV-9\nHandling Fee USD 40.00") -> bytes:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    data = pdf.tobytes()
    pdf.close()
    return data


def blank_pdf_bytes() -> bytes:
    import fitz

    pdf = fitz.open()
    pdf.new_page()
    data = pdf.tobytes()
    pdf.close()
    return data


def png_bytes(size=(40, 20)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def jpg_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(buf, format="JPEG")
    return buf.getvalue()


def tiff_bytes(frames: int = 2) -> bytes:
    from PIL import Image

    images = [Image.new("L", (20, 20), 255) for _ in range(frames)]
    buf = io.BytesIO()
    images[0].save(buf, format="TIFF", save_all=True, append_images=images[1:])
    return buf.getvalue()


def bills_json_bytes() -> bytes:
    return json.dumps([{"_synthetic": True, "bill_id": "SYN-B-1"}]).encode("utf-8")


def eml_bytes(
    *,
    plain: str | None = f"{SYNTHETIC_MARK}\nPlease update Handling Fee to USD 45.00",
    html: str | None = "<html><body><p>SYNTHETIC TEST DATA</p><p>Handling Fee <b>USD 45.00</b></p></body></html>",
    attachments: list[tuple[str, str, bytes]] | None = None,
    nested: bytes | None = None,
    subject: str = "SYNTHETIC 测试 Pre-Alert",
) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "Synthetic Sender <sender@example.com>"
    msg["To"] = "Receiver One <r1@example.com>, r2@example.com"
    msg["Date"] = "Fri, 30 Oct 2026 10:00:00 +0800"
    msg["Message-ID"] = "<synthetic-1@example.com>"
    if plain is not None:
        msg.set_content(plain)
    if html is not None:
        if plain is None:
            msg.set_content(html, subtype="html")
        else:
            msg.add_alternative(html, subtype="html")
    for filename, mime, data in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    if nested is not None:
        from email import policy
        from email.parser import BytesParser

        inner = BytesParser(policy=policy.default).parsebytes(nested)
        msg.add_attachment(inner)
    return msg.as_bytes()
