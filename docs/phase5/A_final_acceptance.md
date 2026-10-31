> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# A. 最终功能验收报告

生成时间：2026-10-30（Phase 5）  
依据：`docs/requirements.md`、真实运行产物 `output/`

## 结论摘要

系统在 **解析、真实 DeepSeek 提取、业务规则、JSON、Streamlit** 上达到可交付水平。  
**OSS 签名 URL → OCR 网关** 仍为 **FAILED/BLOCKED**，不得标为 OCR 全链路通过。  
PNG 样例在 OCR 未打通前 **无法提取费用**（诚实空结果，非冒充成功）。

### 提交前业务复核（2026-10-30）

- PDF1：`accounting_entity=NEPTUNE SHIPPING LIMITED` → **CREATE + AP**（非此前误报的 AR）。  
- 根因：LLM 常把 Consignee 填成 issuer；修复为付款方向线索优先。  
- OCR：签名 URL 504、PNG 真实 OCR **仍未通过**（见 D / 验收矩阵）。

## 十项核心验收（招聘方）

| # | 要求 | 状态 | 证据 |
|---|------|------|------|
| 1 | 正确解析 EML 正文及附件 | **已实现且真实验证** | `test_real_samples_parsing`；样例验收 EML 产出 H/C $50 PENDING_REVIEW |
| 2 | 调用 OCR API 识别 PDF/图片 | **已实现但外部联调失败（签名 URL）**；公开 URL OCR **PASSED**；样例侧 OCR 上传默认关闭 | `docs/ocr_gateway_diagnosis.md`；acceptance JSON 中 `ocr_api: 0` |
| 3 | 解析 Excel、Word 费用表 | **已实现但只有合成/单测验证**；DOC 需 LibreOffice **BLOCKED** | `test_office_and_pdf_parsers` |
| 4 | 提取单据号、费用、金额、币种 | **已实现且真实验证（PDF/EML 文本层+LLM）**；PNG **受阻** | real_llm 5/5；acceptance |
| 5 | 区分新增/更新账单 | **已实现；合成账单真实验证**；招聘方未提供真实已有账本 | phase3 单测 + PDF2 与合成账单 L1 歧义→PENDING_REVIEW |
| 6 | 记账主体判断 AR/AP | **已实现且真实验证** | PDF1 CREATE+**AP**（Neptune=付款方，收付款方向优先于 issuer）；`test_payment_direction_ar_ap` |
| 7 | 重复账单与冲突检测 | **已实现；合成验证** | matcher / validator 单测；PDF2 多候选 |
| 8 | 数据校验与 JSON 稳定性 | **已实现且真实验证** | `delivery_valid: true`；schema 六字段块 |
| 9 | ≥5 点设计思考 | **已实现** | README §12（10 点） |
| 10 | Python + LangChain | **已实现且真实验证** | Agent + tool_trace |

## 功能分类汇总

### 已实现且真实验证

- EML/PDF 文本层解析、表格拆分
- DeepSeek Tool Calling + 结构化提取（EML/PDF1/PDF2）
- 条件性费用排除（PDF1）
- 三行费用保留（PDF2）
- H/C $50 币种 null → PENDING_REVIEW
- JSON 六字段块校验与下载路径
- Streamlit 五页壳 + AppTest 上传跑数
- 安全基础（大小、路径、嵌套邮件、密钥不入库）

### 已实现但只有模拟/单测

- Excel/XLSX、DOCX
- UPDATE/NO_CHANGE 精细路径（合成 fixture）
- OCR Client 异常分支（MockTransport）

### 已实现但外部联调失败

- 私有 OSS 签名 URL → OCR HTTP 504
- 因此：**招聘方样例真实 OCR 端到端未宣称通过**

### 尚未实现 / 受阻

- DOC（无 LibreOffice）
- PNG 费用提取（依赖 OCR 打通）
- 招聘方真实已有账单 JSON（未提供）
