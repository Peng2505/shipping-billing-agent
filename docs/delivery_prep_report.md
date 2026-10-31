# 最终交付准备报告（人工验收前草稿）

状态：**等待人工 Streamlit 点击验收** — 在招聘方/本人反馈前，**不**认定为最终交付版本，**不** push / **不**打 ZIP。

生成时间：2026-10-30

---

## A. 自动化测试统计

| 套件 | 结果 | 备注 |
|------|------|------|
| `pytest tests/unit` + Streamlit 冒烟 | **169 passed**（人工验收前） | `output/demo_session/pytest_pre_human.txt` |
| Streamlit AppTest 冒烟 | 有 | `tests/integration/test_streamlit_app.py` |
| LocalTunnel / HMAC / R2 安全单测 | 有 | 不冒充 OCR 成功 |
| 决策 Pipeline 脚本 | `scripts/demo/pipeline_decision_acceptance.py` | CREATE/AR·AP/NO_CHANGE/PENDING/UPDATE |

---

## B. PDF/PNG 真实 OCR

见 `docs/exam_ocr_acceptance_matrix.md` 与 `output/final_exam_acceptance/latest_report.json`：  
**真实 E2E** 网关 PASSED；CREATE+AR/AP 在证据充分时通过。

---

## C. CREATE / UPDATE / NO_CHANGE / PENDING_REVIEW

| 操作 | 层级 |
|------|------|
| CREATE + AR/AP | 真实 Pipeline（合成 PDF；OCR 可选） |
| NO_CHANGE | 真实 Pipeline + 合成已有账单 JSON |
| PENDING_REVIEW（金额差异无证据） | 真实 Pipeline |
| UPDATE | 决策引擎 + ChangeRequest（与 Agent grounding 同路径）；界面 amend 依赖模型抽出变更句 |
| L1–L4 / 歧义 | 单元 / 模拟通过 |

---

## D. Streamlit 五页

自动化：冒烟 + 有数据 session 绑定。  
**人工验收关卡：** 见启动后暂停说明（本对话）。

---

## E. LocalTunnel 一键启停

- `scripts/demo/Start-ExamDemo.ps1` / `Stop-ExamDemo.ps1`
- `scripts/demo/start_exam.py` / `stop_exam.py`
- 不复用过期 status；仅杀本会话 PID

---

## F. 干净环境复现

| 步骤 | 本轮 |
|------|------|
| 清除 status / 停旧 Tunnel / 新 URL 启动 | **已验证**（同机） |
| 全新克隆到另一台电脑 + 新 venv | **文档可推断，本轮未做异机** → 不得标「全新环境 PASSED」 |
| 仅合成文件、控制 OCR 次数 | **已设计** |

---

## G. 笔试要求矩阵

见 [`docs/exam_ocr_acceptance_matrix.md`](exam_ocr_acceptance_matrix.md)（持续更新人工结果）。

---

## H. 独立 Git

目标：`git rev-parse --show-toplevel` = `d:/shipping-billing-agent`（或交付副本路径）。  
**禁止**在 `D:/` 根执行 add/commit/push。  
人工验收通过后再做最终安全检查与拟提交清单确认。

---

## I. 敏感信息

- `.env` gitignore；不提交
- `output/` gitignore
- `tools/cloudflared.exe` gitignore
- README **不含**动态 Tunnel URL
- **`screenshots/` 允许纳入 Git**：正式人工验收证据；保留 `PDF1` / `PDF2` / `EML` / `PNG` / `Synthetic`
- **不要**将整个 `screenshots/` 加入 `.gitignore`
- 提交前须检查截图无 API Key、访问令牌、完整临时 Tunnel / 签名 URL（本轮二进制扫描未命中密钥类子串；服务卡片仅显示「已配置」）

---

## J. 限制

OSS/R2 OCR 504；Quick Tunnel 非生产；DOC 需 LibreOffice；OCR 可能漏 MBL。

---

## K. 是否具备提交 GitHub

**否（本阶段）** — 待人工验收全部完成后再判定；**当前不执行 `git push`**。
