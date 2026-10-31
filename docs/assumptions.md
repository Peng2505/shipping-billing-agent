# 假设、已验证信息与风险

> 状态：Phase 5（2026-10-30）已完成最终验收报告；详见 `docs/phase5/`。每阶段更新。
> 标记说明：**[已确认]** 用户或题目明确；**[默认]** 非关键事项采用的安全默认；**[待确认]** 影响财务正确性，未确认前按保守方式处理。

## 1. 输入数据清单（实际扫描结果）

| # | 文件 | 大小 | 真实格式 | 需要 OCR | 说明 |
| --- | --- | --- | --- | --- | --- |
| 1 | `深圳容宇 PRE-ALERT SSZSE26093128 VASINGER LLC 1x40HQ  CNTR NO._ TIIU8975975   MBL NO._ OOLU4055331281  Arrived time 2026-10-30.eml` | 1,479,995 B | EML (multipart/mixed) | 内嵌 JPEG、两个 PDF 附件 | 文件名含中文、连续空格、`_` 替代 `:` |
| 2 | `PDF示例账单1.pdf` | 151,278 B | PDF 1.4，3 页，有文本层 | 是（题目要求） | Oracle Reports 生成 |
| 3 | `PDF 示例账单2.pdf` | 77,705 B | PDF 1.4，1 页，有文本层，含 2 张图片 | 是 | wkhtmltopdf 生成，文件名含空格 |
| 4 | `图片示例.png` | 91,964 B | PNG | 是（唯一文本来源） | ZIM Invoice |

- 项目中**不存在**招聘方提供的已有账单 JSON。[已确认]
- 4 个文件之间的提单号、箱号均不相同，**不假设属于同一笔业务**。

## 2. 真实样例分析与预期结果

机器可读的期望值见 [`tests/expected/real_samples.yaml`](../tests/expected/real_samples.yaml)。期望值由人工阅读原文得出，只用于断言，不被业务代码读取。

### 2.1 EML（PRE-ALERT）

| 项 | 内容 | 来源 |
| --- | --- | --- |
| Subject | `深圳容宇 PRE-ALERT SSZSE26093128 VASINGER LLC 1x40HQ  CNTR NO.: TIIU8975975   MBL NO.: OOLU4055331281  Arrived time 2026-10-30` | 邮件头 |
| From / To | `luka@pltplt.com` → `li@pltplt.com` | 邮件头 |
| Date | 2026-10-20 15:46:44 +0800 | 邮件头 |
| 结构 | `multipart/mixed` → `multipart/related` → `multipart/alternative`(plain 518B, html 6188B) + 内嵌 `InsertPic_C25B.jpg`(cid, 794,853B, 1125×578) ；附件 `4055331281 MBL.pdf`(165,901B)、`4055331281 HBL.pdf`(113,664B)，MIME 均声明为 `application/octet-stream` | MIME |
| 正文关键内容 | MBL/HBL Telex release HOLD；YANTIAN → LONG BEACH CY/CY FREIGHT PREPAID；AMS `GSDRHZMHK331281`；MBL `OOLU4055331281`；ATD 2026-10-15；ETA 2026-10-30；`Carrier Free H/C`；`SHA pay TAR：H/C $50` | plain 与 html 内容一致 |
| MBL 附件 | B/L 栏 `4055331281`（无 OOLU 前缀），Shipper SUN TRACK EXPRESS (CHINA)，Consignee/Notify TARGETING A INC，容器 `TIIU8975975/OOLLHV6833`，818 CTNS，无费用 | 文本层 |
| HBL 附件 | B/L `SSZSE26093128`，Export ref `OOLU4055331281`，Shipper SHENZHEN XUELANG TRADING，Consignee VASINGER LLC，FREIGHT PREPAID，无费用 | 文本层 |
| 内嵌 JPEG | 内容未知，需 OCR 确认（可能为签名图） | — |

预期：
- 唯一疑似费用 `H/C $50`：金额 50，**币种 null**（只有 `$` 符号），交易主体 SHA/TAR **不映射为公司**，operation = `PENDING_REVIEW`。[已确认]
- `Carrier Free H/C` 是免收说明，**不是费用**。
- `H/C` 不在题目费用字典中，确定性映射结果为未知；LLM 可给出“建议名 Handling Charge”，但只作为建议，不作为标准名。[待确认：是否把 `H/C` 加入字典]

### 2.2 PDF 示例账单 1（CMA CGM Arrival Notice）

| 项 | 内容 |
| --- | --- |
| 单据类型 | Arrival Notice（GENERAL NOTICE），不是 Invoice/Debit Note |
| 单据编号 | 无明确发票号 → `reference_no = null` |
| B/L | `CMDUCHN4053601`（`B/L #` 栏 `CHN4053601` + SCAC `CMDU`） |
| 箱号 | `SAPU2040689`（ISO 6346 校验位正确），封号 C9950614，20ST |
| 船名/航次 | CMA CGM LYRA / MTE070W19 |
| 出现的公司 | NEPTUNE SHIPPING LIMITED（地址块重复出现）、CIMC WETRANS INTL LOG CO LTD（Shipper）、CMA CGM (AMERICA) LLC（Remit to / 页 3）、CMA CGM & ANL Securities BV（Beneficiary） |
| 实际费用 | `On Carriage Additional - US Em`（代码 OCA17），USD 245.0000 |
| 合计 | `TOTAL CHARGES TO BE PAID: 245.0000`，与实际费用一致 |
| 条件/说明性金额（排除） | I.T. 取消服务费 $25.00（每页重复 1 次，共 3 次）；SOC 误还箱费 $1100；司机等待超时 $150/小时 |

预期：只输出 1 条费用 USD 245.00；三个条件性金额必须排除并在审计中记录。签发方不能仅凭 Remit to 认定 [已确认]。收付款方向证据：`Please Pay` / `TOTAL CHARGES TO BE PAID` + Consignee=`NEPTUNE SHIPPING LIMITED`，Remit to=`CMA CGM (AMERICA) LLC` → Neptune 为付款方。当 `accounting_entity=NEPTUNE SHIPPING LIMITED` 时 → **AP**（不得因 LLM 误把 Consignee 填成 issuer 而判成 AR）。交易双方证据不足且无付款方向强线索时 → `posting_type=null` + `PENDING_REVIEW`。

### 2.3 PDF 示例账单 2（Neptune Debit Note）

| 项 | 内容 |
| --- | --- |
| 单据类型 / 编号 | DEBIT NOTE / `DC-108478` |
| 日期 | D/C DATE `10-24-2026`；DUE DATE `10-24-2026` |
| 日期格式证据 | 同文件内 `08-30-2026`（POL ETD）、`10-28-2026`（ETA）第二段 > 12 → 本文件为 `MM-DD-YYYY`，`document_date = 2026-10-24` |
| TERMS / 币种 | `COD` / `USD` |
| 关联字段 | MBL `MAEU275752922`，HBL `CGT260801188`，箱号 `MRSU2571577`、`TCLU8619685`（均校验通过），OUR FILE `OI-26090566`，AGENT FILE `CGTSE260801188` |
| 费用（3 行，P/C 均为 `C`） | ① HANDLING CHARGE 65.00 ② 4 ADD'L DETENTION FREE TIME CHARGE 1,310.40 ③ HANDLING CHARGE 35.00 |
| 合计 | TOTAL 1410.40，PAID AMOUNT 0.00；3 行合计 = 1410.40 ✓ |
| 方向证据 | `GRAND TOTAL BALANCE DUE TO NEPTUNE SHIPPING LIMITED (LAX)`；`BENEFICIARY : NEPTUNE SHIPPING LIMITED` |
| 接收方 | 文本层中**未找到** Bill To，可能在图片中，需 OCR 补充 |

预期：3 条独立费用记录；行 ① 与 ③ 同名但金额、行号不同，**不是重复**；`PAID AMOUNT 0.00`、`TOTAL` 不是费用。收款方 = NEPTUNE SHIPPING LIMITED，当 accounting_entity 为 Neptune 时 → AR；其他主体且无付款方证据 → null + `PENDING_REVIEW`。

### 2.4 PNG 图片示例（ZIM Invoice）

| 项 | 内容 |
| --- | --- |
| 单据类型 / 编号 | DEBIT INVOICE（标题 INVOICE）/ `ORFR1618731` |
| 日期 | `Invoice date 10/03/2025`；船名旁 `10/09/2025`（航次日期，不是单据日期）；签章日期 `03/10/2025` |
| 日期歧义 | `10/03/2025` 与 `03/10/2025` 可解读为 MM/DD+DD/MM（10 月 3 日）或 DD/MM+MM/DD（3 月 10 日），文件内没有日 > 12 的证据 → **格式无法由文件证据确定**，不按地理位置猜测：`document_date = null`，保留原文并标记 `DATE_AMBIGUOUS` |
| 签发方 | ZIM AMERICAN INTEGRATED SHIPPING SERVICES CO. LLC AS AGENTS FOR ZIM INTEGRATED SHIPPING SERVICES LTD |
| 接收方 | ALL AMERICA FORWARDING, INC.（Payer: USIAHALLAM） |
| 关联字段 | Booking Number 与 B/L 均为 `ZIMUNGB1312144`；箱号 `JXLU4504463`（校验通过），1 X 40 HC |
| 付款 | Place of payment USORF；Payment Due PAY IMMEDIATELY |
| 费用 | ① WHARFAGE ADMINISTRATION FEE：Base C，Rate 5.00，USD 5.00 ② WHARFAGE：Base 显示为 `ᵖTT`，Rate 2.85，USD 21.90 |
| 合计 | USD 26.90 ✓ |

预期：2 条费用，币种 USD（Curr 列明确）；数量未印出 → `quantity = null`，禁止用 21.90/2.85 反推；`PAY IMMEDIATELY` 不是 PP/CC → payment_term 标准值 null（原文保留）。

**OCR 网关实测（2026-10-31，图片示例.png）：** `orderType=ANR_LLM_ZIM-INVOICE`，`chargeList` 仅有 `chargeItem`/`amount`/`chargeCtr`，且 `chargeCtr=""`（容器号字段，不是币种）；整份 OCR JSON **不含** `USD`。因此在仅依赖 OCR API 证据时，币种必须保持 `null` 并 `PENDING_REVIEW`，不得凭原图目视补造。若 OCR 将来回显 `currency`/`Curr`/`USD`，规则可继承到费用行。

### 2.5 易误判清单（均需测试覆盖）

| 类别 | 场景 |
| --- | --- |
| 条件性/说明性金额 | PDF1 的 $25、$1100、$150/h |
| 合计/已付 | PDF1 TOTAL CHARGES、PDF2 TOTAL / PAID AMOUNT 0.00、PNG 26.90 |
| 同名非重复 | PDF2 两笔 HANDLING CHARGE |
| 免收说明 | EML `Carrier Free H/C` |
| 未知币种 | EML `$50` |
| 缩写主体 | EML SHA / TAR |
| 编号变体 | MBL `4055331281` vs `OOLU4055331281`；PDF1 `CHN4053601` vs `CMDUCHN4053601` |
| 字段相同 | PNG Booking 与 B/L 相同 |
| 日期 | PNG 日期格式歧义；PNG 航次日期 vs 单据日期；PDF2 MM-DD 可由文件内证据确定 |
| OCR 字符 | PNG `ᵖTT`；箱号 O/0、I/1 |
| AR/AP | PDF2 为 Debit Note，但 AR/AP 取决于 accounting_entity |
| 跨文件 | 4 个文件不属于同一业务 |

## 3. 已验证的接口信息

### 3.1 OCR API（`https://gateway.pltplt.com/ai/process`）

2026-10-30 实际请求结果（仅使用公开、不含业务数据的文件 URL，未上传任何样例）：

| 请求 | 结果 |
| --- | --- |
| `GET` / `OPTIONS` | `405 {"detail":"Method Not Allowed"}`，`allow: POST`，nginx/1.24.0 |
| `POST` W3C dummy.pdf，`task=orderChange`，`callBack=""`，`taskType=""` | `200`，17.1 s，同步返回 JSON，无需鉴权头 |
| `POST` 公开示例发票 PDF（slicedinvoices） | `200`，40.0 s，`chargeList` 有 2 项 |
| `POST` 不可达 URL（`example.invalid`） | `504 Gateway Time-out`（nginx HTML，非 JSON），61.8 s |

已观察到的响应结构（样本量 2，**不代表完整契约**）：

```json
{
  "data": {
    "createDate": "2026-10-30 16:53:37", "fileName": "",
    "list": [{
      "fileType": "PAI-COLOADER-NOTICE", "invoiceNumber": "INV-3337", "mblNumber": "",
      "shipper": "", "consignee": "Test Business  \n123 Somewhere St ...",
      "ctrList": [], "chargeList": [{"chargeItem": "Web Design", "amount": "85.00", "chargeCtr": ""},
                                     {"chargeItem": "Tax", "amount": "8.50", "chargeCtr": ""}],
      "hold": {"holdType": "", "holdDate": "", "holdDesc": ""}, "other": [],
      "suspicious": "N", "isDetention": "N", "isDemurrage": "N", "page_index": [0, 1],
      "customsClearance": "", "customsReleaseStatus": "", "firmsCode": "", "cyFirmsCode": "",
      "inlandArrivalDate": "", "loadedOnRailDate": "", "itNumber": "", "itDate": "", "itLocation": "",
      "pickupLocation": "", "remark": "", "revisedEtaOfDestination": "", "usCustomsStatus": ""
    }],
    "orderType": "ANC_GLOBAL FREIGHT SERVICE-INVOICE", "pages_split": [[0, 1]]
  },
  "success": true, "message": "文档处理成功", "error_code": null, "task_id": null
}
```

结论与设计影响：
1. `task=orderChange` 返回的是**结构化业务字段**，不是原始 OCR 全文。系统将完整原始响应保存为 `origin=ocr_api` 的证据块，交给 Agent 与其他来源交叉验证；不自行编造字段映射。
2. `chargeList` 只有 `chargeItem / amount(字符串) / chargeCtr`，**无币种、无数量**；`Tax` 会作为普通 chargeItem 出现 → 币种必须来自其他明确证据，税行需单独识别。
3. 非业务文档也返回 `fileType=PAI-COLOADER-NOTICE`，`fileType` 不能直接作为单据类型。
4. 不可达 URL 表现为约 60 s 后 nginx 504 HTML → Client 必须处理非 JSON 响应；签名 URL 有效期需覆盖 OCR 处理时间（默认 30 min 足够）。
5. 未确认：`taskType`、`callBack` 的语义与取值；`suspicious` 的判定含义；图片（PNG/JPG/TIFF）格式下的响应差异；`success=false` 时的结构；文件大小限制；并发/频率限制。**在用真实样例验证前，不声称接口已完全验证。**

### 3.2 其他

- 大模型：DeepSeek `deepseek-flash` via `api.deepseek.com` [已验证]。Tool Calling 可用；原生 `response_format` 不可用，Agent 使用 ToolStrategy。必须 `thinking.type=disabled`，否则 tool_choice 强制会 400。真实样例提取 5/5 PASSED（2026-10-30）。
- 阿里云 OSS：私有 Bucket 上海公网 Endpoint 已验证：上传、签名 HTTPS GET、本地下载、删除均 PASSED；未授权对象返回 403。

### 3.3 OSS → OCR 联调结论（合成文件，2026-10-30）

| 步骤 | 结果 |
| --- | --- |
| OSS put + private ACL | PASSED |
| 签名 URL 本机 GET | PASSED（HTTPS，~2s） |
| 未签名 URL GET | 403（保持私有） |
| OCR POST(file=签名URL) | FAILED HTTP 504 ~65s（nginx Gateway Time-out） |
| 临时对象删除 | PASSED |
| PublicEndpointForbidden | **未出现** |

分类：`OCR_GATEWAY_TIMEOUT_FETCHING_FILE`（OCR 上游拉取文件失败/超时），不是 RAM 权限错误、不是签名错误、也不是上海 PublicEndpointForbidden。

对比：同一 OCR 网关对公开 W3C dummy PDF 可在 ~17s 成功。说明 OCR 服务本身可用，但对 `*.oss-cn-shanghai.aliyuncs.com` 签名 URL 拉取失败或过慢。

**最小必要调整方案（需你确认后再做，不擅自改云权限/开付费资源）：**
1. 向 OCR 服务方确认其出网是否可访问 `*.aliyuncs.com` / 是否需加白名单。
2. 若可启用且你同意费用：OSS 传输加速域名（`oss-accelerate.aliyuncs.com`）后再测签名 URL。
3. 备选：仅对已授权文件使用 OCR 方可访问的临时托管；**禁止**把 Bucket 改为公共读。
4. 招聘方真实样例在获得数据使用授权前不上传（测试需 `AUTHORIZE_SAMPLE_OCR=1`）。

## 4. 业务假设与决策

| # | 事项 | 决策 | 标记 |
| --- | --- | --- | --- |
| B1 | `$` 符号 | 不换算为 USD；币种 null → PENDING_REVIEW；UI 可显示“候选 USD”但不进入输出 | 已确认 |
| B2 | 缩写主体（SHA、TAR） | 不映射为具体公司；保留原文证据 | 已确认 |
| B3 | Arrival Notice | 只保留实际费用；签发方不能仅凭 Remit to 认定；不明确则 null + 视风险 PENDING_REVIEW | 已确认 |
| B4 | 已有账单 JSON 格式 | 未提供；合成 fixture 采用输出记录的 6 个字段块 + 内部 `bill_id`（以及可选的 bl_no/booking_no/container_no 匹配字段）；文件标记 `_synthetic: true` | 已确认 |
| B5 | 同名费用 L1 多候选 | 用非金额明确证据（箱号、提单号、日期、付款条款、行号映射）消歧；金额只能辅助；不唯一 → PENDING_REVIEW | 已确认 |
| B6 | 交付 JSON | 严格 6 个字段块，不扩展；追踪信息写入 `processing_report.json` | 已确认 |
| B7 | 日期格式 | 仅依据文件内证据（同文件中日 > 12 的日期、月份文字、ISO 格式）判定；无法判定 → `document_date=null` + `DATE_AMBIGUOUS` 警告，保留原文 | 已确认（原则）/ 默认（是否阻断：不阻断 CREATE，阻断 L4 匹配） |
| B8 | 付款方式标准化 | `PREPAID`/`P`/`FREIGHT PREPAID` → `PP`；`COLLECT`/`C`（P/C 列）→ `CC`；`COD`、`PAY IMMEDIATELY` 等付款条件保留原文、标准值 null | 默认 |
| B9 | `H/C` | 已加入确定性字典 → Handling Charge；但必须结合行级上下文区分 `Carrier Free H/C`（waived）与 `H/C $50`（actual）。`$` 仍不转 USD | 已确认 |
| B10 | 税行 | 作为独立费用行保留并标注 `nature=tax`，是否单独输出待真实样例出现时确认；当前样例无税行 | 默认 |
| B11 | 记账主体 | 由用户输入；名称比较做大小写/标点/公司后缀规范化，并支持配置别名；不做模糊语义匹配 | 默认 |
| B12 | 人工复核 | UI 中的“确认/驳回”只改变会话状态和导出标注，不写回原始账单 | 默认 |
| B13 | 幂等 | 指纹 = 文件 sha256 + 明细行序号 + 规范化 key；同一运行中重复指纹只处理一次；对已有账单中已存在相同指纹的记录不再 CREATE | 默认 |

## 5. 技术选择

| 选择 | 原因 |
| --- | --- |
| `billing_agent/` 包名 | 避免与入口 `app.py` 同名冲突（偏离 AGENTS.md 推荐的 `app/`，职责划分不变） |
| 项目内 `.venv` | 本机为 Anaconda base 环境，独立虚拟环境保证可复现 |
| LangChain `create_agent` + `ChatOpenAI(base_url)` | 单 Agent，少量只读工具 + Pydantic `response_format`；兼容各家 OpenAI 接口 |
| PyMuPDF | PDF 文本层、表格、页面渲染预览；已安装且稳定 |
| openpyxl / xlrd | XLSX / XLS（xlrd 2.x 仅支持 .xls） |
| python-docx + LibreOffice | DOCX 原生解析；DOC 通过 `soffice --headless --convert-to docx` 转换 |
| oss2 | 阿里云官方 OSS Python SDK，支持 STS 与签名 URL |
| 静态 ISO 4217 表 | 避免额外依赖，便于审计 |
| 魔数识别 | EML 附件 MIME 声明不可靠（样例为 octet-stream） |

## 6. 需求覆盖矩阵

状态：`NOT_STARTED` / `IN_PROGRESS` / `DONE(测试证据)` / `BLOCKED(原因)`。最后更新：Phase 5（详见 docs/phase5/G_requirements_matrix.md）。

| 需求 | 来源 | 模块 | 测试 | 状态 |
| --- | --- | --- | --- | --- |
| EML 头部/正文(plain+html)/附件 | req §3.2 | parsers/email_parser | test_email_parser, test_real_samples_parsing | DONE（单测 + 真实样例） |
| EML 嵌套递归 + 安全限制 | req §3.2 | email_parser, dispatcher | test_email_parser(nested/depth/count) | DONE（合成数据） |
| 附件按真实格式解析 | req §3.2 | dispatcher | test_dispatcher, 真实样例 octet-stream→PDF | DONE |
| PDF 文本/表格 | req §3.1 | pdf_parser | test_office_and_pdf_parsers, 真实样例 | DONE（文本层）；OCR 部分见下 |
| JPG/PNG/TIFF | req §3.1 | image_parser + ocr_service | test_ocr_service_and_storage（Fake） | IN_PROGRESS（真实 OCR BLOCKED） |
| XLS/XLSX | req §3.1 | excel_parser | test_office_and_pdf_parsers（合成） | DONE（合成数据） |
| DOC/DOCX | req §3.1 | word_parser | test_office_and_pdf_parsers | DOCX DONE；DOC BLOCKED（无 LibreOffice，已验证明确报错） |
| JSON 已有账单 | req §3.3 | json_parser, bill_store | test_dispatcher（json） | IN_PROGRESS（语义校验在 Phase 3） |
| OCR Client 独立封装 | req §4 | services/ocr_client | test_ocr_client（MockTransport） | DONE（Mock） |
| OCR 超时/失败/非预期响应 | req §4 | ocr_client | test_ocr_client | DONE（Mock，504 HTML 场景来自真实观测） |
| 本地文件 → 安全 URL | req §4.1 | services/oss_storage, ocr_service | test_ocr_service_and_storage（Fake）, real_oss | IN_PROGRESS（真实 OSS BLOCKED） |
| 真实 OCR 调用 | req §4, §15.3 | ocr_client | integration real_ocr 契约探测（公开文件） | 契约探测 PASSED；真实样例 BLOCKED（无 OSS） |
| 字段提取（单据/关联/费用） | req §5 | agents/extraction_agent | unit wiring + real_llm | IN_PROGRESS（真实 LLM BLOCKED：无 Key） |
| 证据关联 | req §5, AGENTS §5.3 | agents/tools, grounding | test_grounding_and_tools | DONE（单元/脚本化期望） |
| 费用名称标准化 | req §6 | charge_normalizer | test_charge_normalizer（含 H/C vs Carrier Free） | DONE（确定性映射） |
| OCR chargeList 过滤 | assumptions §3.1 | ocr_charge_filter | test_ocr_charge_filter | DONE（Mock/合成） |
| CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW | req §7 | decision_engine | test_phase3_business_rules | DONE（合成 fixture） |
| UPDATE 仅改有依据字段 | req §7.2 | bill_updater | test_phase3_business_rules | DONE |
| 四级匹配优先级 + 歧义 | req §8 | bill_matcher | test_phase3（含两笔 HC 歧义） | DONE |
| AR/AP | req §9 | ar_ap_classifier | test_phase3 | DONE |
| 12 项校验 | req §10 | validator, date_parser, currency | test_phase3 | DONE（主体路径） |
| 标准 JSON 输出 | req §11 | json_builder | test_phase3 | DONE |
| Streamlit 五页面 | req §12 | ui/* + pipeline | AppTest + streamlit run | DONE（OCR 失败态如实展示） |
| 安全（大小/路径/递归/密钥/脱敏） | req §14 | security, config | test_security | NOT_STARTED |
| 测试场景 1–20 | req §15 | tests/ | 见上 | NOT_STARTED |
| 8 点设计思考 | req §16 | README | 人工检查 | NOT_STARTED |
| 交付物 | req §17 | 根目录 | 人工检查 | NOT_STARTED |

## 7. 风险与阻塞项

| # | 风险 / 阻塞 | 影响 | 应对 | 状态 |
| --- | --- | --- | --- | --- |
| R1 | OSS→OCR 网关拉取签名 URL 超时 | 同字节公开 URL OCR PASSED；OSS 签名 URL OCR 504；分类 OCR_GATEWAY_TIMEOUT_FETCHING_FILE | 详见 docs/ocr_gateway_diagnosis.md；服务方排查说明已写好；不启用加速/不改公共读 | OPEN |
| R2 | DeepSeek flash 默认 thinking 拒绝 tool_choice | create_agent ToolStrategy 400 | 默认 `LLM_THINKING=disabled` 经 `extra_body` 关闭 thinking；真实 LLM 5/5 PASSED | RESOLVED |
| R3 | OCR 不返回原文、无币种字段 | 图片唯一来源为结构化字段，币种可能无法确认 | 原始响应作为证据；币种缺失 → PENDING_REVIEW；可选：经确认后引入视觉模型作为额外来源 | OPEN |
| R4 | OCR 不可达时 60 s 504 | 用户等待长、需正确报错 | 超时配置、HTML 响应识别、UI 显示失败原因 | OPEN |
| R5 | `taskType`/`callBack` 语义未知 | 可能未用最优任务模式 | 保持题目示例取值；记录未验证 | OPEN |
| R6 | 无 LibreOffice | DOC 无法解析 | 明确报错；DOC 测试 BLOCKED；README 说明安装 | BLOCKED |
| R7 | 样例含真实银行账户、客户信息 | 数据外发/日志泄露 | 仅发往指定 OCR；日志脱敏；签名 URL 不入日志 | OPEN |
| R8 | 无真实已有账单 | UPDATE/NO_CHANGE 只能用合成数据验证 | 合成 fixture 明确标记 | OPEN |
| R9 | D:\ 根目录为 git 仓库 | 误提交风险 | 项目内独立 `.gitignore`；需要时在项目目录 `git init` | OPEN |
| R10 | PyMuPDF 2.0 在本机 venv 中 `import fitz` 直接崩溃（0xC0000005） | PDF 解析不可用 | 固定 `PyMuPDF>=1.26,<1.28`（实测 1.27.2.3 正常） | RESOLVED |
| R11 | 真实 EML 附件名含不换行空格（`4055331281\xa0MBL.pdf`） | 文件名比对/显示异常 | 清洗时统一为普通空格，原始名保存在 `meta.original_filename`；已加回归测试 | RESOLVED |
| R12 | PDF 表格检测把多行费用合并为一行（PDF2） | 费用行丢失/合并 | 通用规则：各单元格行数一致且 > 1 时拆行，否则不拆；已加单测与真实样例测试 | RESOLVED |
| R13 | OCR 网关无法在超时内拉取阿里云上海 OSS 签名 URL | 合成文件 OCR end-to-end FAILED(504)；OSS 本身 PASSED | 最小调整见 §3.3；不改 Bucket 为公共读；不擅自上传招聘方样例 | OPEN |
| R14 | OCR chargeList 过滤规则修正 | 不得无条件丢弃 Tax；不得仅因金额=合计而排除 | 已改 ocr_charge_filter：Tax 保留为 nature=TAX；合计相等不自动排除 | RESOLVED |

## 8. 测试数据规则

- `data/samples/`：真实样例，只读，不修改、不改名。
- `data/fixtures/synthetic/`：合成数据，文件名前缀 `synthetic_`，JSON 内含 `"_synthetic": true`，Excel/Word 首行或首段写明 `SYNTHETIC TEST DATA`。
- `tests/expected/`：人工核对的期望值，注明证据位置；业务代码不得读取。
- Mock / Fake 仅存在于 `tests/unit`；真实外部调用仅存在于 `tests/integration` 并带 marker。
