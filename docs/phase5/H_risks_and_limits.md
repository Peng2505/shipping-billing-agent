> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# H. 项目仍然存在的风险和限制

| ID | 风险 | 影响 | 缓解 / 现状 |
|----|------|------|-------------|
| R1 | OSS 签名 URL → OCR 504 | 无法对私有托管文件完成题目 OCR 全链路；PNG/扫描依赖此链路 | 诊断完备；等服务方；不改公共读 |
| R2 | 招聘方样例外发合规 | 未授权上传可能泄密 | 默认关闭 OCR 上传；需显式勾选 |
| R3 | 无真实已有账单 JSON | UPDATE/NO_CHANGE 场景覆盖偏合成 | fixture 标记 `_synthetic`；UI 演示模式说明 |
| R4 | PDF2 × 合成账单 L1 歧义 | 操作多为 PENDING_REVIEW 而非 CREATE | 符合安全优先；可换空账单库演示 CREATE |
| R5 | DOC 依赖 LibreOffice | 旧 Word 无法解析 | 明确报错；README 说明 |
| R6 | OCR 结构化响应无币种 | 仅 OCR 时币种常缺失 | PENDING_REVIEW；交叉文本层 |
| R7 | Streamlit 原生 Upload 英文文案 | 观感不够「全中文」 | 框架限制；标签中文已覆盖 |
| R8 | LLM 非确定性 | 偶发字段措辞差异 | temperature=0；规则兜底；断言抓关键金额 |
| R9 | 误提交 .env / output | 密钥与业务数据泄露 | gitignore；交付前人工检查 |
| R10 | 面试现场网络依赖 | DeepSeek/OCR 不可达则提取/OCR 失败 | 预跑结果与离线单测；错误态可见 |

## 不夸大声明清单

- 不说「OCR 全链路已通」  
- 不说「PNG 费用已提取成功」  
- 不说「Mock OCR = 真实 OCR」  
- 不说「演示模式 = 假 Pipeline」——Pipeline 真实，已有账单可合成  
