> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# B. 真实样例结果对照报告

来源：`scripts/phase5_sample_acceptance.py` → `output/phase5_sample_acceptance.json`  
条件：**OCR 上传关闭**；已有账单 = 合成 fixture；LLM = DeepSeek（已配置）。

## 对照总表

| 样例 | 期望（assumptions） | 本次结果 | 验证类型 |
|------|---------------------|----------|----------|
| EML | H/C $50，币种 null，PENDING_REVIEW；Free H/C 非费用 | PENDING_REVIEW×1，Handling Charge amount=50 currency=null；excluded≥1 | **真实 LLM + 解析**；内嵌图 OCR **未跑** |
| PDF1 | 仅 USD 245；排除 $25/$1100/$150；Neptune 记账 → AP | CREATE×1 amount=245.0000 USD；**posting_type=AP**；actual=1 excluded≥3 | **真实 LLM + PDF 文本层**（非 OCR） |
| PDF2 | 三行 65 / 1310.40 / 35；合计 1410.40 | 三行金额齐全；ops=PENDING_REVIEW×3（合成账单 L1 歧义/字段冲突） | **真实 LLM + 文本层**；匹配保守 |
| PNG | 两行 + 合计 26.90 | 0 费用；OCR NOT_CONFIGURED / 未授权上传 | **诚实空结果**；**非 OCR 成功** |

## 分项说明

### EML

- 邮件头/附件解析此前单测已过。
- Agent `tools=35`，`actual_charges=1`。
- `CURRENCY_UNCONFIRMED` → PENDING_REVIEW（符合 `$` 不转 USD）。
- **不得**声称附件 JPEG OCR 成功。

### PDF1

- `text_layer` blocks=3，`ocr_api`=0。
- UI/警告明确：text_layer ≠ OCR success。
- **CREATE + AP**（`accounting_entity=NEPTUNE SHIPPING LIMITED`）。
- 依据：Please Pay / TOTAL TO BE PAID + Consignee=Neptune（付款方）；Remit to / address block = CMA CGM (AMERICA) LLC（收款方）。不得因 LLM 把 Consignee 填成 issuer 而误判 AR。
- 复核证据：`output/phase5_pdf1_arap_recheck.txt`、`tests/unit/test_payment_direction_ar_ap.py`。

### PDF2

- 提取金额正确；`delivery_valid=true`，3 条记录。
- PENDING_REVIEW 原因含「Multiple candidates at L1」及字段无证据变更警告 — **财务安全优先**，不是漏提取。
- 若清空合成已有账单再跑，预期更易落 CREATE（未在本轮改 fixture 强行「刷绿」）。

### PNG

- 无文本块、无 OCR → 不发明费用。
- 要达到期望费用，必须先解决 OSS→OCR 504，并获数据外发授权。

## 标签纪律

| 标签 | 本轮适用 |
|------|----------|
| 真实 LLM 提取通过 | EML、PDF1、PDF2 |
| PDF 文本层解析通过 | PDF1、PDF2 |
| 真实 OCR 通过 | **否**（样例未走通签名 URL OCR） |
| 模拟测试通过 | Excel/Word/匹配合成路径等 |
| 尚未测试或受阻 | PNG 费用、DOC、签名 URL OCR |
