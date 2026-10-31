
# AGENTS.md

## 1. 项目身份

项目名称：
多格式文档解析的航运智能账单助手智能体

英文名称：
Shipping Billing AI Agent

项目类型：
Python + LangChain + Streamlit AI Agent 应用

本项目是一份真实的 AI Agent 工程笔试。

目标是交付可运行、可测试、可解释、具有可视化界面的航运账单处理系统，而不是仅能展示的静态 Demo。

## 2. 最高优先级规则

开始任何开发工作前，必须阅读：

1. docs/requirements.md
2. AGENTS.md
3. docs/architecture.md（如果存在）
4. docs/assumptions.md（如果存在）

业务需求的优先级：

1. 原始笔试硬性要求
2. docs/requirements.md
3. 已确认的项目架构和业务决策
4. 当前用户指令
5. 通用工程建议

如果发现冲突，应明确指出并以原始笔试硬性要求为准，不得自行忽略需求。

## 3. 开发目标

必须实现：

- 多格式文档解析
- 真实 OCR API 集成
- LangChain 结构化信息提取
- 费用名称标准化
- 已有账单匹配
- CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW
- AR/AP 判断
- 财务数据校验
- 标准 JSON 输出
- Streamlit 可视化系统
- 自动化测试及交付文档

禁止以静态页面或硬编码数据替代真实功能。

## 4. 技术栈

必须使用：

- Python
- LangChain

优先使用：

- Streamlit
- Pydantic
- pytest
- requests/httpx
- openpyxl
- python-docx
- python-dotenv

如需增加依赖，先说明用途。

使用当前稳定且互相兼容的 API，不要混用过时和新版 LangChain 接口。

优先采用简单、稳定、易维护的方案。

## 5. 开发原则

### 5.1 AI 与确定性规则解耦

LLM 负责：

- 文档语义理解
- 单据分类
- 字段提取
- 费用名称辅助识别
- 从文字中识别明确的变更意图

Python 规则负责：

- 账单匹配
- 金额校验
- 币种校验
- 费用去重
- 更新字段控制
- AR/AP 业务判断
- CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW 决策

禁止让大模型在没有校验的情况下直接决定财务入账结果。

### 5.2 不得虚构数据

禁止：

- 猜测缺失金额
- 猜测币种
- 猜测交易双方
- 猜测单据编号
- 自行生成不存在的账单
- 无依据地修改已有账单
- 将模型推测当作已验证事实

无法确认的字段使用 null。

高风险情况使用 PENDING_REVIEW。

### 5.3 保留可追踪性

所有重要输出应能够追踪到：

- 原始文件
- 原始文本或表格
- 提取字段
- 费用标准化结果
- 匹配依据
- 更新依据
- 校验结果
- 最终操作类型

审计信息应简洁、具体、可核验。

不得伪造模型内部推理过程。

### 5.4 禁止伪造执行结果

禁止声称：

- 没有调用的 API 已调用成功
- 未执行的测试全部通过
- Mock OCR 等于真实 OCR
- 静态页面等于功能已完成
- 仅能解析样例就等于支持所有格式

任何成功结论都必须有实际执行证据。

## 6. 推荐工程结构

建议采用以下目录组织：

shipping-billing-agent/
├── AGENTS.md
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── cli.py
│   ├── schemas.py
│   ├── config.py
│   ├── pipeline.py
│   │
│   ├── parsers/
│   │   ├── email_parser.py
│   │   ├── pdf_parser.py
│   │   ├── image_parser.py
│   │   ├── excel_parser.py
│   │   └── word_parser.py
│   │
│   ├── agents/
│   │   └── extraction_agent.py
│   │
│   ├── services/
│   │   └── ocr_client.py
│   │
│   ├── business/
│   │   ├── charge_normalizer.py
│   │   ├── bill_matcher.py
│   │   ├── bill_updater.py
│   │   ├── ar_ap_classifier.py
│   │   └── validator.py
│   │
│   └── ui/
│       ├── dashboard.py
│       ├── document_view.py
│       ├── bill_review.py
│       ├── audit_view.py
│       └── json_output.py
│
├── data/
│   └── samples/
│
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   └── assumptions.md
│
├── tests/
│   ├── test_parsers.py
│   ├── test_extraction.py
│   ├── test_matching.py
│   ├── test_ar_ap.py
│   ├── test_validation.py
│   └── test_integration.py
│
└── output/

该结构是推荐方案，可根据实际工程情况合理调整，但必须保持职责分离。

## 7. Streamlit 开发规范

可视化界面是正式交付的一部分。

必须包含：

1. Dashboard 工作台
2. 文档解析中心
3. 账单核对中心
4. AI 决策与审计
5. JSON 输出中心

UI 风格：

- 企业级 SaaS 后台
- 简洁、现代
- 蓝白灰为主
- 清晰的导航和布局
- 明确的处理状态
- 适度的统计卡片
- 真实业务数据驱动

要求：

- UI 调用真实业务服务。
- 不在 Streamlit 页面中重复实现核心业务规则。
- 使用 session_state 管理当前会话状态。
- 不得伪造处理进度或业务结果。
- 错误信息必须可见。
- Demo Mode 必须显式标注。
- JSON 结果必须可以下载。
- 不需要额外开发复杂 React 前端。

## 8. 数据模型规范

优先使用 Pydantic 定义：

- ParsedDocument
- DocumentInfo
- TransactionParty
- ChargeDetails
- FinancialAttributes
- BillRecord
- ProcessingResult
- AuditTrail

模型名称可调整，但字段意义必须明确。

要求：

- 类型约束
- 缺失值使用 Optional/null
- 金额使用 Decimal 进行内部运算
- 序列化输出为合法 JSON
- 保留原始值和标准化值
- 保留来源证据
- 最终输出符合题目结构

不能随意增加与原始 JSON 格式冲突的字段。

## 9. 业务规则规范

### 9.1 账单匹配

严格执行 requirements.md 指定的四级匹配优先级。

多个候选无法唯一确认时，进入 PENDING_REVIEW。

### 9.2 账单更新

UPDATE 只能修改有明确依据要求变化的字段。

其余字段保持原值。

不得用新提取对象直接覆盖已有账单对象。

### 9.3 AR/AP

必须基于 accounting_entity 和交易方向判断。

不能根据 Debit Note 或 Credit Note 单独判断。

### 9.4 人工复核

当关键数据不足或存在冲突时，优先保证财务安全。

不得为了追求自动化率强行执行更新。

## 10. OCR API 规范

使用指定 OCR Endpoint：

https://gateway.pltplt.com/ai/process

必须：

- 独立封装 OCR Client
- 处理接口超时和失败
- 支持合法、可访问的文件 URL
- 验证真实响应字段
- 记录必要的响应状态
- 对识别错误进行检测
- 不把 Mock 结果冒充真实接口结果

在实际确认 API 响应结构之前，不得编造字段映射。

若无法完成真实 OCR 调用，应明确记录阻塞因素及未完成项。

## 11. 安全要求

- 不提交 .env 和 API Key。
- .gitignore 必须排除密钥及敏感临时文件。
- 外部 URL 必须进行安全验证。
- 上传文件设置大小和类型限制。
- 防止路径穿越和恶意文件名。
- 解析嵌套邮件时设置深度限制。
- 不在日志中泄露密钥或敏感账单内容。
- 不在未确认的情况下修改原始账单数据。
- 不自动将测试数据上传到公开服务，除非为题目指定 OCR 所必需且符合数据使用授权。

## 12. 开发方式

必须采用分阶段开发。

### Phase 0：需求分析和规划

- 阅读所有需求文件。
- 检查 data/samples。
- 列出需求覆盖矩阵。
- 识别接口和业务歧义。
- 确定项目结构。
- 编写 docs/architecture.md。
- 编写 docs/assumptions.md。

本阶段不应一次性生成完整项目代码。

### Phase 1：文档解析

实现不同格式的解析器。

验证原始文本、表格、邮件和附件能够被正确读取。

### Phase 2：LangChain Agent

实现模型配置、结构化提取、证据关联和字段校验。

### Phase 3：业务规则引擎

实现费用标准化、匹配、账单更新、AR/AP 和数据验证。

### Phase 4：Streamlit Web UI

实现五个可视化模块，并接入真实业务 Pipeline。

### Phase 5：测试、优化与交付

运行自动化测试、真实样例和完整 UI 流程。

补全文档，检查交付物。

## 13. 每个阶段的验收要求

每完成一个阶段，必须：

1. 说明完成了哪些功能。
2. 列出修改或新增的文件。
3. 运行相关测试。
4. 给出真实测试结果。
5. 明确失败、阻塞和未验证事项。
6. 检查是否影响已有功能。
7. 说明下一阶段计划。

不得仅用“代码已生成”作为完成标准。

## 14. 测试纪律

必须使用 pytest。

规则：

- 不允许删除失败测试以制造通过结果。
- 不允许降低断言来掩盖 bug。
- 不允许硬编码测试样例输出。
- 不允许把 Mock 测试伪装成集成测试。
- 修复 bug 后应增加回归测试。
- 外部服务不可用时必须说明。
- 测试结果必须来自真实运行。

## 15. 修改代码时的规则

修改现有代码前：

1. 先阅读相关模块。
2. 理解现有接口和调用关系。
3. 尽量采用最小必要修改。
4. 不随意重构已经稳定的模块。
5. 不删除已有功能。
6. 不引入无必要的新框架。
7. 保持函数和模块职责清晰。

遇到错误时先定位根因，不要盲目重写整个项目。

## 16. 文档要求

README.md 必须包含：

- 项目简介
- 技术栈
- 系统架构
- 安装方法
- API 配置
- Web 启动命令
- CLI 使用说明
- 输入输出示例
- 测试运行方法
- 已知限制
- 业务和技术设计思考

docs/assumptions.md 必须记录：

- 未明确的业务规则
- 技术选择原因
- 已验证的接口信息
- 尚未解决的限制
- 对测试数据的假设

## 17. 开发完成定义

只有满足以下条件，才能声称项目完成：

- 核心业务流程实际运行成功。
- Python 与 LangChain 已实际使用。
- Streamlit 界面可正常启动。
- 文件上传连接真实解析流程。
- CREATE/UPDATE/NO_CHANGE/PENDING_REVIEW 正确实现。
- AR/AP 判断具备证据。
- JSON 输出合法。
- 关键自动化测试通过。
- README 能指导他人在新环境运行。
- 外部依赖和已知限制有明确说明。

如果某项未完成，必须真实报告，不得宣称完全达标。

## 18. 与用户沟通规范

- 使用中文解释开发进展。
- 代码、函数、变量采用规范英文命名。
- 解释应简单、具体、直接。
- 优先报告实际完成结果。
- 明确区分实现成功、测试成功和推测。
- 遇到非关键歧义可采取安全合理的默认设计，并记录假设。
- 遇到影响财务正确性的歧义不能擅自猜测。
- 不要反复要求用户确认已经明确的事项。

## 19. 项目核心原则

本项目的目标不是让 AI 做所有事情。

而是：

让 AI 理解文档；
让规则保证财务正确性；
让测试验证功能；
让 Streamlit 展示完整过程。

以业务正确性、工程可靠性和可解释性为最高优先级。
