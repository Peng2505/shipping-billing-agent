# 合成笔试样例（无客户敏感数据）

| 文件 | 用途 |
|------|------|
| `exam_debit_create.pdf` | CREATE + AR/AP（PDF，含 text_layer） |
| `exam_debit_create.png` | CREATE 路径 + 真实 OCR（勾选授权） |
| `exam_debit_amend.pdf` | 费用行 125.50 + amend from 100.00 to 125.50；配合 update JSON → UPDATE |
| `exam_debit_create.pdf` + `existing_bills_update.json` | 无 amend 句、金额 125.50 vs 账本 100 → PENDING_REVIEW |
| `existing_bills_no_change.json` | 金额已是 125.50 → 期望 NO_CHANGE |
| `existing_bills_update.json` | 金额 100.00；有明确 amend 证据 → UPDATE，否则 PENDING_REVIEW |

记账主体：

- `NEPTUNE SHIPPING LIMITED` → AR
- `ACME FREIGHT CONSIGNEE LLC` → AP

关闭「使用模拟已有账单」后，再上传上表 JSON。
