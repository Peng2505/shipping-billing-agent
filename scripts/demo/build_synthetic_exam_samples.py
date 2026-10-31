"""Build non-sensitive synthetic Debit Note PDF/PNG + existing-bill JSON for human demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "samples" / "synthetic_exam"
MBL = "LTFINALMBL9001"
REF = "DC-FINAL-9001"
AMOUNT = "125.50"
CURRENCY = "USD"
CHARGE = "HANDLING CHARGE"
PAYEE = "NEPTUNE SHIPPING LIMITED"
PAYER = "ACME FREIGHT CONSIGNEE LLC"


def make_pdf(path: Path, *, amend_line: str | None = None) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    extra = f"\n{amend_line}\n" if amend_line else "\n"
    text = f"""DEBIT NOTE
Reference No: {REF}
MBL Number: {MBL}
CURRENCY: {CURRENCY}

BENEFICIARY
{PAYEE}

CONSIGNEE
{PAYER}

Please Pay freight against the master B/L shown below
TOTAL CHARGES TO BE PAID:
{AMOUNT}
{extra}
Charge Details:
{CHARGE}    {AMOUNT} {CURRENCY}
TOTAL {AMOUNT} {CURRENCY}

SYNTHETIC EXAM SAMPLE — NOT CUSTOMER DATA
"""
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(path)
    doc.close()


def make_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1200, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        "DEBIT NOTE",
        f"Reference No: {REF}",
        f"MBL Number: {MBL}",
        f"CURRENCY: {CURRENCY}",
        "BENEFICIARY",
        PAYEE,
        "CONSIGNEE",
        PAYER,
        "Please Pay freight against the master B/L",
        f"TOTAL CHARGES TO BE PAID: {AMOUNT}",
        f"{CHARGE}  {AMOUNT} {CURRENCY}",
        f"TOTAL {AMOUNT} {CURRENCY}",
        "SYNTHETIC — NOT CUSTOMER DATA",
    ]
    y = 30
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 32
    img.save(path, format="PNG")


def bill(amount: str, bill_id: str) -> dict:
    return {
        "_synthetic": True,
        "bill_id": bill_id,
        "document_type": "Debit Note",
        "reference_no": REF,
        "issuer": PAYEE,
        "recipient": PAYER,
        "bl_no": MBL,
        "charge_item": "Handling Charge",
        "charge_item_raw": CHARGE,
        "amount": amount,
        "currency": CURRENCY,
        "accounting_entity": PAYEE,
        "posting_type": "AR",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    make_pdf(OUT / "exam_debit_create.pdf")
    make_png(OUT / "exam_debit_create.png")
    make_pdf(
        OUT / "exam_debit_amend.pdf",
        amend_line=(
            "Please amend the HANDLING CHARGE amount from 100.00 USD "
            "to 125.50 USD as agreed."
        ),
    )
    (OUT / "existing_bills_no_change.json").write_text(
        json.dumps(
            {"_synthetic": True, "bills": [bill(AMOUNT, "SYN-EXAM-HC-125")]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "existing_bills_update.json").write_text(
        json.dumps(
            {"_synthetic": True, "bills": [bill("100.00", "SYN-EXAM-HC-100")]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        f"""# 合成笔试样例（无客户敏感数据）

| 文件 | 用途 |
|------|------|
| `exam_debit_create.pdf` | CREATE + AR/AP（PDF，含 text_layer） |
| `exam_debit_create.png` | CREATE 路径 + 真实 OCR（勾选授权） |
| `exam_debit_amend.pdf` | 配合 `existing_bills_update.json` 测 UPDATE / PENDING |
| `existing_bills_no_change.json` | 金额已是 {AMOUNT} → 期望 NO_CHANGE |
| `existing_bills_update.json` | 金额 100.00 → 有明确 amend 证据时期望 UPDATE，否则 PENDING_REVIEW |

记账主体：

- `{PAYEE}` → AR
- `{PAYER}` → AP

关闭「使用模拟已有账单」后，再上传上表 JSON。
""",
        encoding="utf-8",
    )
    print(f"Wrote samples under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
