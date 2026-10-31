> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# G. 笔试要求达标矩阵

对照 `docs/requirements.md` §2 / §18 及核心能力。状态定义：

- **V**：已实现且真实验证  
- **M**：已实现但主要靠模拟/单测  
- **E**：已实现但外部联调失败  
- **N**：尚未实现或受阻  

| 需求项 | 状态 | 备注 |
|--------|------|------|
| EML/PDF/JPG/PNG/TIFF/XLS/XLSX/DOC/DOCX/JSON | V/M/N | DOC=N(LibreOffice)；PNG OCR=E/N |
| EML 头正文附件递归 | V | |
| 题目 OCR API 集成 | E | 公开 URL V；签名 URL E |
| 字段提取 | V | PDF/EML；PNG 受阻 |
| 费用/币种/付款标准化 | V/M | |
| CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW | V/M | 真实样例多见 CREATE/PENDING；UPDATE 合成 |
| AR/AP | V | PDF1 Neptune→AP（付款方向证据）；非硬编码 |
| 重复/冲突/低置信 | V/M | |
| 来源与依据保留 | V | |
| 标准 JSON | V | |
| Streamlit | V | |
| 真实测试与文档 | V | 本目录 + README |
| Python + LangChain | V | |
| 安全与 .gitignore | V | |
| ≥8 设计思考 | V | README |
| OSS 签名 URL OCR | E | **未通过** 504；见 D_ocr_leftover |
| PNG 真实 OCR | N/E | **未验证通过** |

## §15 测试场景覆盖（摘要）

多数业务场景由 `tests/unit/test_phase3_business_rules.py`、`test_payment_direction_ar_ap.py`、真实样例解析/LLM、acceptance 覆盖。  
Streamlit E2E：`test_phase5_e2e_apptest` + 手工浏览器空态/结构检查。  
真实 OCR 样例端到端：**未标 PASSED**（签名 URL 504；PNG 未通过）。
