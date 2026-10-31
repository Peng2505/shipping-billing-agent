
# 多格式文档解析的航运智能账单助手智能体
# Project Requirements

## 1. 项目背景

航运及国际货代业务的费用信息通常分散在 EML 邮件、PDF 账单、扫描图片、Excel 费用表和 Word 文档中。

财务人员需要人工识别 Debit Note、Credit Note、Invoice 等单据中的费用项目、金额、币种、付款方式和应收应付属性，再新增账单或更新已有账单。

本项目要求基于 Python 和 LangChain 构建 AI Agent，通过多格式文档解析、OCR 识别、大模型语义分析和确定性业务规则，自动完成航运费用信息提取、账单匹配、账单新增与更新，并生成标准 JSON。

除原始笔试要求外，本项目增加 Streamlit 可视化 Web 系统，方便展示完整处理过程。

## 2. 项目目标

系统必须支持：

1. EML、PDF、JPG、PNG、TIFF、XLS、XLSX、DOC、DOCX 等数据源。
2. 自动解析 EML 邮件标题、发件人、收件人、正文及附件。
3. 使用题目指定 OCR API 识别 PDF 和图片。
4. 提取单据编号、费用、金额、币种等业务信息。
5. 标准化费用名称、币种及付款方式。
6. 根据输入信息新增账单或更新已有账单。
7. 根据当前记账主体和交易方向判断 AR/AP。
8. 识别重复账单、冲突数据和低置信度结果。
9. 保留文件来源、原始文本和处理依据。
10. 输出符合约定格式的合法 JSON。
11. 提供可运行的 Streamlit Web 系统。
12. 提供真实测试、使用文档和可交付源码。

### 2.1 硬性技术要求

- Python
- LangChain

### 2.2 推荐辅助技术

- Streamlit：可视化界面
- Pydantic：结构化数据及校验
- requests/httpx：OCR API 调用
- openpyxl：XLSX 解析
- xlrd 或其他兼容方案：XLS 解析
- python-docx：DOCX 解析
- DOC 兼容读取方案：旧版 Word 文件解析
- pytest：自动化测试
- python-dotenv：环境变量管理

可以使用必要的其他依赖，但应避免无意义地增加复杂度。

## 3. 输入数据

### 3.1 支持格式

| 格式 | 需要解析的内容 |
| --- | --- |
| EML | 邮件标题、收发件人、正文、附件 |
| PDF | 文本、扫描页、表格及费用信息 |
| JPG/PNG/TIFF | OCR 文字识别 |
| XLS/XLSX | 工作表、表格、费用明细行 |
| DOC/DOCX | 文本段落、表格、费用内容 |
| JSON | 已有账单，用于匹配与更新 |

### 3.2 EML 特殊要求

- 正确识别邮件头部和正文。
- 支持纯文本和 HTML 正文。
- 解析所有支持格式的附件。
- 根据附件真实文件格式选择解析器。
- 支持嵌套 EML 的递归处理，并设置合理的安全限制。
- 邮件正文和附件中的数据可能互相补充或冲突。
- 保留邮件及附件来源信息。

### 3.3 已有账单

输入可以包含一个已有账单 JSON 文件。

系统必须读取其内容并用于：

- 已有账单匹配
- 判断 CREATE/UPDATE/NO_CHANGE
- 保留未修改字段
- 检测重复记录
- 发现新旧数据冲突

## 4. OCR API

PDF 和图片必须集成题目提供的 OCR API。

API Endpoint:

https://gateway.pltplt.com/ai/process

题目提供的 Python 调用示例：

```python
import requests

file_url = "https://example.com/bill.pdf"
url = "https://gateway.pltplt.com/ai/process"

data = {
    "file": file_url,
    "task": "orderChange",
    "callBack": "",
    "taskType": ""
}

response = requests.post(
    url,
    json=data,
    timeout=(10, 300)
)
response.raise_for_status()

ocr_result = response.json()
```

要求：

1. `file` 应为 OCR 服务端能够访问的 PDF 或图片下载地址。
2. 不能直接使用本地文件路径冒充在线 URL。
3. 接口需要封装成独立 OCR Client。
4. 支持超时、网络错误和非预期响应处理。
5. 不得自行假设 OCR 响应结构。
6. 通过真实请求确认返回字段和实际识别效果。
7. 未确认 `task`、`taskType` 含义前，不得声称接口已完全验证。
8. OCR 失败时报告错误，不得假装识别成功。
9. 可使用 Mock 进行单元测试，但必须与真实 API 测试明确区分。
10. OCR 输出需要保留与源文件的对应关系。

### 4.1 本地文件的 OCR 处理

如果 OCR API 仅接受远程文件 URL，需要实现安全的上传或文件访问适配方式。

不得将本地路径直接传入 `file`。

如果没有可用的上传机制，应明确标记当前限制，不得使用虚假的公网地址。

## 5. 航运业务信息提取

系统应从文档中提取：

### 5.1 单据信息

- document_type：单据类型
- reference_no：单据编号
- document_date：单据日期
- issuer：签发方
- recipient：接收方

应支持识别：

- Debit Note
- Credit Note
- Invoice
- 其他能够确定的航运费用单据

### 5.2 业务关联字段

- Bill of Lading Number：提单号
- Booking Number：订舱号
- Container Number：箱号
- 交易双方
- 相关日期

这些字段主要用于已有账单匹配。

### 5.3 费用信息

- 原始费用名称
- 标准费用名称
- 数量
- 单价
- 金额
- 币种
- 付款方式
- 小计
- 税额
- 总计

所有字段必须以实际文档证据为基础。

无法确认的字段使用 null。

一份单据可能包含多个费用项目，每个有效费用项目应独立形成一条输出记录。

## 6. 费用名称标准化

建立可扩展的费用名称映射表。

| 原始名称 | 标准名称 |
| --- | --- |
| Handling Fee | Handling Charge |
| H/D Fee | Handling Charge |
| Doc Fee | Documentation Fee |
| THC | Terminal Handling Charge |
| Trucking Fee | Trucking Charge |
| Customs Fee | Customs Clearance Fee |
| Storage Fee | Storage Charge |

要求：

1. 优先采用可维护的确定性映射表。
2. 对未知费用名称可以使用 LLM 辅助识别。
3. 不得强行将无法确认的费用映射为已有分类。
4. 同时保留原始名称和标准名称。
5. 后续能够方便地扩展费用字典。

## 7. 账单处理规则

支持四种 operation：

- CREATE
- UPDATE
- NO_CHANGE
- PENDING_REVIEW

### 7.1 CREATE

当输入文件包含有效费用，且没有匹配到已有账单时，执行 CREATE。

要求：

- 每个费用项目生成独立记录。
- 不得生成重复账单。
- 必须通过必要的字段和财务校验。
- 信息不足以安全处理时转人工复核。

### 7.2 UPDATE

当识别到已有账单，且存在明确的修改依据时，执行 UPDATE。

更新只能修改输入材料中有明确证据要求变化的字段。

不得覆盖没有明确修改要求的原有字段。

例如：

已有账单：

- Handling Charge
- USD 40.00
- Payment Term: PP

新邮件明确要求将金额修改为 USD 45.00。

正确结果：

- operation = UPDATE
- amount = 45.00
- currency = USD
- payment_term = PP

其余未要求修改的字段保持原值。

### 7.3 NO_CHANGE

匹配到已有账单，且确认没有需要修改的字段时，执行 NO_CHANGE。

### 7.4 PENDING_REVIEW

存在以下情况时应根据风险进入人工复核：

- 匹配到多个候选账单，无法唯一确定。
- OCR 关键字段识别不可靠。
- 金额或币种存在未解决冲突。
- 缺少关键业务信息。
- AR/AP 无法可靠判断。
- 同一费用存在矛盾的多来源证据。
- 无法确定具体应修改哪些字段。

不能为了得到 CREATE 或 UPDATE 而忽略异常。

## 8. 已有账单匹配

严格按以下优先级执行：

1. 单据编号 + 费用名称
2. 提单号 + 费用名称 + 币种
3. 订舱号 + 费用名称 + 币种
4. 箱号 + 交易双方 + 日期 + 金额

要求：

- 优先使用更高优先级的可靠匹配结果。
- 费用名称比较前先标准化。
- 匹配字段缺失时不能凭空补充。
- 多个候选不能随意选择第一条。
- 保留匹配规则及匹配依据。
- 避免同一已有账单被错误重复更新。
- 不允许仅凭模糊语义相似度决定更新目标。

## 9. AR/AP 应收应付判断

系统必须从当前记账主体 accounting_entity 的视角判断。

AR = Accounts Receivable，应收账款。

AP = Accounts Payable，应付账款。

需要综合考虑：

1. 当前记账主体
2. 签发方 issuer
3. 接收方 recipient
4. 实际收费方
5. 实际付款方
6. 费用收付方向
7. 单据类型及付款条款

不能仅凭 Debit Note 或 Credit Note 直接判断 AR/AP。

记账主体必须由用户输入或明确配置提供。

无法判断时，posting_type 应为 null，并标记需要人工复核，不得猜测。

## 10. 数据校验

系统必须实现以下校验：

1. 金额是否为有效数字。
2. 金额运算采用 Decimal，避免浮点精度问题。
3. 币种是否符合 ISO 4217。
4. 币种使用三位字母代码，如 USD、CNY。
5. 明细金额与合计金额是否一致。
6. OCR 是否存在 O/0、I/1 等识别混淆。
7. 同一费用是否被重复提取。
8. 多份材料是否存在冲突。
9. 是否存在关键字段缺失。
10. 输出是否符合约定 JSON 结构。
11. 更新是否仅修改明确要求的字段。
12. 重复执行相同输入是否导致错误重复新增。

校验失败必须保留可追踪的错误或复核信息。

## 11. 标准 JSON 输出

最终输出必须是合法的 JSON 数组。

每个费用项目输出一条独立记录。

基本结构：

```json
[
  {
    "operation": "UPDATE",
    "document_info": {
      "document_type": "Debit Note",
      "reference_no": "DN-202609-001",
      "document_date": "2026-09-20"
    },
    "transaction_party": {
      "issuer": "Destination Agent",
      "recipient": "Origin Agent"
    },
    "charge_details": {
      "charge_item": "Handling Charge",
      "amount": 40.00,
      "currency": "USD",
      "payment_term": "PP"
    },
    "financial_attributes": {
      "accounting_entity": "Origin Agent",
      "posting_type": "AP"
    },
    "audit_trail": {
      "ai_reasoning": [
        "通过单据编号和费用名称匹配到已有账单",
        "根据原始材料确认本条费用需要更新",
        "没有明确修改依据的字段保持原值"
      ]
    }
  }
]
```

上述内容仅为格式示例，不代表真实测试结果。

### 11.1 字段约定

operation：
账单操作类型。

document_info：
单据类型、编号、日期。

transaction_party：
单据签发方和接收方。

charge_details：
费用名称、金额、币种及付款方式。

financial_attributes：
当前记账主体和应收应付属性。

audit_trail：
简短、可核验的处理依据。

`ai_reasoning` 应记录业务依据和处理摘要，而不是虚构或输出模型内部隐藏推理过程。

### 11.2 输出要求

- 顶层必须是数组。
- 每条记录必须符合定义的数据结构。
- 金额必须使用 JSON 数字类型。
- 缺失字段使用 JSON null。
- 同一币种统一表示为三位字母代码。
- 严格区分原始数据、模型提取结果和最终决策。
- 其他内部追踪字段可保存在独立的中间结构中，避免随意改变交付 JSON 格式。

## 12. Streamlit 可视化系统（新增展示需求）

要求实现一个真实可操作的 Web 应用。

该功能是项目主动增加的工程展示要求，不属于原始笔试明确规定的必需技术栈。

### 12.1 Dashboard 工作台

提供：

- 应用标题和导航菜单
- 多格式文件上传
- 已有账单 JSON 上传
- accounting_entity 配置
- 启动 Agent 按钮
- 当前处理阶段和状态
- 文件总数、费用数、CREATE 数、UPDATE 数、待复核数
- 真实错误提示

### 12.2 文档解析中心

提供：

- 已上传文件列表
- 文件类型和解析状态
- 邮件正文和附件信息
- PDF/图片 OCR 结果
- Excel/Word 表格内容
- 结构化提取字段
- 原始内容与提取结果的对应关系

### 12.3 账单核对中心

提供：

- 费用明细表
- CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW 筛选
- AR/AP 信息
- 原始账单与拟更新账单对比
- 真正变化字段的高亮显示
- 冲突和风险提示

### 12.4 AI 决策与审计

提供：

- 费用标准化依据
- 使用的账单匹配规则
- AR/AP 判定依据
- 信息缺失及冲突情况
- 简明审计记录
- 人工复核状态

### 12.5 JSON 输出中心

提供：

- 最终 JSON 预览
- JSON Schema/Pydantic 校验
- JSON 下载按钮
- 错误信息及处理说明

### 12.6 UI 原则

- 使用简洁、专业的企业级后台风格。
- 推荐蓝、白、灰配色。
- Streamlit 只负责界面，业务逻辑不得写死在 UI 中。
- 展示的数据必须来自真实处理结果。
- 不得将模拟数据伪装为真实运行结果。
- Demo Mode 必须明显标识。
- 不应为了 UI 美观降低核心业务正确性。

## 13. 核心系统架构

推荐处理流程：

文件输入
  ↓
文件类型识别
  ↓
EML/PDF/图片/Excel/Word 解析
  ↓
OCR API（PDF/图片）
  ↓
统一文档中间结构
  ↓
LangChain + LLM 字段提取
  ↓
Pydantic 结构化校验
  ↓
费用名称与付款方式标准化
  ↓
已有账单匹配
  ↓
AR/AP 判断
  ↓
账单新增/更新/复核决策
  ↓
财务数据验证
  ↓
标准 JSON 输出
  ↓
Streamlit 结果展示及下载

设计原则：

AI 主要负责理解非结构化文档。

Python 规则引擎负责关键财务判断、匹配及校验。

不得完全依赖 LLM 自主生成最终财务决策。

## 14. 工程及安全要求

- 核心业务逻辑与 Streamlit 页面解耦。
- 提供可运行的项目入口。
- API Key 放入环境变量。
- 提供 .env.example，不提交真实密钥。
- 上传文件设置大小限制。
- 防止路径穿越、恶意附件和递归解析失控。
- 处理临时文件并及时清理。
- 外部 OCR 下载地址需要安全检查。
- 不记录不必要的客户敏感数据。
- 错误信息应可定位但不泄漏密钥。
- 关键业务操作应有日志和审计信息。
- 不自动将尚未确认的更新写回原始账单。

## 15. 测试要求

使用 pytest。

至少包含以下测试场景：

1. EML 邮件正文与附件解析。
2. 多种文件格式的解析。
3. PDF/图片真实 OCR 调用。
4. OCR API 超时和失败处理。
5. 一个文件包含多个费用项目。
6. 费用名称标准化。
7. CREATE 业务判断。
8. UPDATE 及未变字段保留。
9. NO_CHANGE 判断。
10. PENDING_REVIEW 判断。
11. 账单匹配优先级。
12. 匹配歧义检测。
13. AR/AP 判定。
14. OCR 易混淆字符检测。
15. 重复费用检测。
16. 缺失字段处理。
17. 多来源金额冲突。
18. JSON 结构校验。
19. 相同输入重复运行的幂等性。
20. Streamlit 调用真实后端的端到端流程。

必须区分以下测试状态：

- PASSED：实际执行并通过。
- FAILED：执行但失败。
- BLOCKED：因外部依赖等原因受阻。
- NOT_TESTED：尚未执行。

不能将 Mock 测试结果冒充真实 OCR 集成测试结果。

## 16. 需要体现的设计思考

项目文档中至少说明以下八点：

1. AI 信息提取与财务规则解耦。
2. 文档证据来源与审计追踪。
3. OCR 低置信度处理与人工复核。
4. 同一输入重复处理的幂等性。
5. 邮件正文和附件冲突解决机制。
6. 财务金额精度及币种校验。
7. 费用名称映射和规则可扩展性。
8. API、上传文件及敏感数据安全。

## 17. 交付物

原始笔试要求：

- 项目代码 ZIP，或 Git 仓库链接。

项目应包含：

- 完整源代码
- requirements.txt
- .env.example
- README.md
- AGENTS.md
- docs/requirements.md
- docs/architecture.md
- docs/assumptions.md
- 自动化测试
- JSON 输出示例
- Streamlit Web 应用

README 应明确描述：

- 环境安装
- API 配置
- Web 启动方式
- CLI 使用方式（如有）
- 输入数据格式
- JSON 输出格式
- 测试运行命令
- 已验证功能
- 已知限制

## 18. 笔试验收标准

原题明确提出：

1. 正确解析 EML 邮件正文及附件。
2. 调用 OCR API 识别 PDF 和图片。
3. 解析 Excel、Word 中的费用表格。
4. 准确提取单据编号、费用、金额和币种。
5. 区分新增账单和更新账单。
6. 结合记账主体判断 AR/AP。
7. 检测重复账单和数据冲突。
8. 数据校验与 JSON 设计能够满足稳定性和输出准确性要求。
9. 写出五点以上对题目的业务或技术补充思考。
10. 基于 Python 和 LangChain 实现。

最终是否满足验收，以真实测试运行结果为依据。

## 19. 未明确事项与处理原则

以下事项在当前题目中仍可能存在歧义：

- OCR API 实际返回结构及鉴权方式。
- `orderChange` 是否对应 OCR 任务类型。
- 本地文件如何生成 OCR 服务可访问的 URL。
- 原始资料中不同金额的优先级。
- 自动判定付款方向所需的最小证据。
- 人工复核确认后的业务处理方式。
- 旧版 DOC 和 XLS 的具体兼容环境。
- 最终 JSON 是否允许扩展额外字段。

解决原则：

1. 优先通过样例、接口响应和原始要求确认。
2. 无法确认时采用保守、安全、可解释的设计。
3. 在 docs/assumptions.md 中记录假设。
4. 不得擅自补造业务数据。
5. 不得将未验证功能标记为完成。
