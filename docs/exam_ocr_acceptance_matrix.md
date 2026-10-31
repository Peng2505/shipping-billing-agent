# 笔试硬性要求最终验收矩阵

生成时间：2026-10-30（终验）  
证据目录：`output/final_exam_acceptance/`、`output/local_tunnel_acceptance/`、本文件。

> **与历史 phase5 报告的关系：** `docs/phase5/` 为阶段性记录；若写「PNG OCR 未打通」，指当时 OSS/签名 URL 阻塞。**LocalTunnel 路径随后已真实打通 PDF/PNG OCR。**  
> **招聘方 ZIM PNG：** 费用金额可过；若网关不回显可靠币种 → `currency=null` + `PENDING_REVIEW`（见 README §16）。OSS/R2→OCR 仍可能 HTTP 504。

## 状态定义

| 标记 | 含义 |
|------|------|
| **真实 E2E** | 本轮真实调用外部 OCR / LLM / Tunnel，有运行证据 |
| **模拟通过** | 确定性规则 / 解析 / 安全单测或合成夹具，未走外网 OCR |
| **部分支持** | 功能存在，但缺依赖、缺样例或字段不完整 |
| **尚未验证** | 本轮未跑或外部环境阻塞 |

---

## A. FileUrlProvider 与 OCR

| Provider | 存储/安全 | OCR 网关拉取 | 总评 |
|----------|-----------|--------------|------|
| `aliyun_oss` | 模拟通过（签名/私有） | **尚未验证本轮**；历史 **504** | 外网阻塞 |
| `cloudflare_r2_worker` | 模拟通过（HMAC/路径） | **尚未验证本轮**；历史 **504** | 外网阻塞 |
| `local_tunnel` | **真实 E2E**（token/过期/401） | **真实 E2E** PDF+PNG | 笔试可用 |

> Quick Tunnel **不是**生产级稳定托管：主机名每次启动变化、无 SLA、关隧道后旧 URL 立即失效（本轮验证：旧 URL → 502；`stop_gateway` 删除 `status.json`；重启得新 URL；`refresh_from_status_file` 不复用过期地址）。

---

## B. 合成 Debit Note：OCR → LangChain → 规则 → JSON

合成件：`output/final_exam_acceptance/final_debit.pdf` / `final_debit.png`  
含：付款方 / 收款方 / 记账主体线索 / MBL=`LTFINALMBL9001` / USD / HANDLING 125.50  
脚本：`scripts/final_exam_acceptance.py` → `latest_report.json`

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | Tunnel 拉取 PDF（SHA） | **真实 E2E** | `tunnel_pdf` PASSED |
| 2 | OCR 网关 PDF | **真实 E2E** | `ocr_gateway_pdf` PASSED；`chargeList` 含 HANDLING 125.50 |
| 3 | OCR 网关 PNG | **真实 E2E** | `ocr_gateway_png` PASSED |
| 4 | OCR JSON 回显 MBL | **部分支持** | `mbl_in_ocr_json=false`（未伪造） |
| 5 | PDF text_layer 持有 MBL | **真实 E2E** | `mbl_from_text_layer=true`；Agent 提取 `bl_no=LTFINALMBL9001` |
| 6 | CREATE + AR（主体=收款方/受益人） | **真实 E2E** | `CREATE×1`，`posting_type=AR`，金额 125.50 USD |
| 7 | CREATE + AP（主体=付款方/收货人） | **真实 E2E** | `CREATE×1`，`posting_type=AP` |
| 8 | 交付 JSON Schema | **真实 E2E** | `delivery_ar.json` 校验通过 |
| 9 | 禁止凭空补造 MBL | **真实 E2E** | `mbl_invented=false`；OCR 未回显时用 text_layer 证据 |

---

## C. 操作类型与匹配优先级

| 操作 / 规则 | 验证方式 | 结果 |
|-------------|----------|------|
| CREATE | 真实 E2E（上表）+ 单测 | **真实 E2E** |
| UPDATE（有 ChangeRequest） | `tests/unit/test_update_no_change_decisions.py` | **模拟通过** |
| NO_CHANGE（字段一致） | 同上 | **模拟通过** |
| PENDING_REVIEW（金额变无证据 / 匹配歧义 / 币种缺失） | 同上 + `test_phase3_business_rules.py` | **模拟通过** |
| L1 唯一匹配 | `test_l1_unique_match` | **模拟通过** |
| L1 多候选歧义（金额不作唯一键） | `test_two_handling_charges_ambiguous_*` | **模拟通过** |
| 非金额消歧 | `test_two_handling_charges_disambiguated_by_line_hint_not_amount` | **模拟通过** |
| AR/AP 不单凭 Debit Note | `test_ar_ap_not_from_debit_note_alone` + payment_direction 单测 | **模拟通过** |
| 真实样例 PDF 全链路 UPDATE/NO_CHANGE | — | **尚未验证**（本轮空账本 CREATE 路径） |

---

## D. 多格式支持（对照招聘方要求）

| 格式 | 解析器 | 本轮验证 | 总评 |
|------|--------|----------|------|
| EML | `email_parser`（头/正文/附件/嵌套深度限制） | 单测 + 真实样例解析/提取（历史） | **模拟通过**；真实 LLM 提取见 `test_real_llm_extraction`（需 `--run-real`） |
| PDF | 文本层 + OCR 路径 | **真实 E2E** OCR+Pipeline | **真实 E2E** |
| PNG | 图 → OCR | **真实 E2E** OCR | **真实 E2E** |
| JPG | 与 PNG 同路径 | 分发/魔数单测 | **模拟通过**（OCR 网关本轮未单独跑 JPG） |
| TIFF | 多帧图解析 | `test_tiff_frames` | **模拟通过**；OCR 本轮未跑 TIFF |
| XLSX | openpyxl | `test_xlsx_rows_*` | **模拟通过** |
| XLS | xlrd | `test_xls_rows` | **模拟通过** |
| DOCX | python-docx | `test_docx_*` | **模拟通过** |
| DOC | LibreOffice 转换 | 无 soffice 时显式 FAILED | **部分支持**（依赖本机 LibreOffice） |
| JSON 已有账单 | bill_store | Phase3 夹具 | **模拟通过** |

---

## E. Streamlit 五页

| 页面 | 验证 | 结果 |
|------|------|------|
| 智能工作台 | AppTest + 注入真实 PipelineResult（合成 PDF text_layer CREATE/AR） | **真实数据绑定通过**（展示 CREATE KPI） |
| 文档解析中心 | 同源 result：blocks / extraction `bl_no` | **真实数据绑定通过** |
| 账单核对中心 | charge / amount / AR / 对比字段 | **真实数据绑定通过** |
| AI 决策与审计 | audit_reasons / posting_reason | **真实数据绑定通过** |
| JSON 结果中心 | schema 六字段块 + 可下载设计 | **真实数据绑定通过** |
| 冒烟（无数据加载） | `tests/integration/test_streamlit_app.py` | **模拟通过** |
| 真实样例 PDF2 全 UI 点击 | `test_phase5_e2e_apptest`（real_llm） | **尚未验证本轮**（需 `--run-real`） |

说明：五页均读取同一 `pipeline_result`，不在页面内重写财务规则。Demo Mode 有显式标注。

---

## F. LocalTunnel 启停

| 步骤 | 结果 |
|------|------|
| README / `docs/local_tunnel_provider.md` 从零启动 | 文档完整；本轮 `start_gateway.py` 成功 |
| `stop_gateway.py` 杀进程并删 `status.json` | **真实验证** |
| 重启后新 `trycloudflare.com` 主机名 | **真实验证**（≠ 旧 URL） |
| Provider 从 status 刷新，不复用过期 URL | **真实验证**（`refresh_from_status_file`） |

---

## G. 自动化回归与安全

| 项 | 结果 |
|----|------|
| `pytest tests/unit` | **166 passed**（原 163 + UPDATE/NO_CHANGE 3） |
| `.env` | 被 `.gitignore` 忽略；未纳入版本库 |
| `output/*` | gitignore；含 OCR 探针 JSON、验收产物（勿打包进提交） |
| `screenshots/` | **允许纳入 Git**（PDF1/PDF2/EML/PNG/Synthetic）；勿整体 gitignore；提交前扫密钥/临时 URL |
| 密钥扫描 | `.env` 含 LLM/OSS/R2/Tunnel token 字段名；勿提交 |
| Quick Tunnel 表述 | README / docs 均标明 **仅开发/笔试，非生产** |

---

## H. 与「总是 PENDING_REVIEW」对照

此前 party 布局不清时规则会 PENDING_REVIEW（财务安全优先）。  
本轮合成件使用明确 BENEFICIARY / CONSIGNEE / Please Pay 证据后：

- 记账主体 = NEPTUNE → **CREATE + AR**
- 记账主体 = ACME → **CREATE + AP**

说明规则在证据充分时**不会**一律 PENDING_REVIEW。

---

## I. 已知限制（诚实披露）

1. OSS / R2 Worker URL 对招聘方 OCR 历史为 504；笔试演示用 LocalTunnel。  
2. OCR `orderChange` 可能不回显自定义 MBL；PDF 可走 text_layer；纯扫描图若 OCR 也未回显则 `bl_no=null`（不编造）。  
3. 旧版 DOC 需 LibreOffice。  
4. JPG/TIFF 真实 OCR 网关本轮未单独复跑（路径与 PNG 相同）。  
5. Quick Tunnel 无生产 SLA。  
6. 本仓库若位于更大磁盘级 git 根下，提交前应确认仅打包本项目且排除 `.env` / `output/`。
