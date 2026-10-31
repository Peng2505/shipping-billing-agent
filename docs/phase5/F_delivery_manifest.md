> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# F. 最终交付文件清单

## 必须交付

| 路径 | 说明 |
|------|------|
| `app.py` | Streamlit 入口 |
| `billing_agent/` | 解析、Agent、业务规则、服务、UI |
| `tests/` | pytest 单元/集成/Phase5 E2E |
| `scripts/phase5_sample_acceptance.py` | 样例验收 |
| `requirements.txt` | 依赖 |
| `.env.example` | 配置模板 |
| `.gitignore` | 密钥与产物排除 |
| `AGENTS.md` | Agent 工程规范 |
| `README.md` | 使用与设计说明 |
| `docs/requirements.md` | 原始需求 |
| `docs/architecture.md` | 架构 |
| `docs/assumptions.md` | 假设与风险 |
| `docs/DESIGN.md` | UI 设计系统 |
| `docs/ocr_gateway_diagnosis.md` | OCR 504 诊断 |
| `docs/phase5/*` | Phase 5 验收报告 A–H |
| `data/samples/` | 招聘方样例（只读） |
| `data/fixtures/synthetic/` | 合成已有账单 |
| `.streamlit/config.toml` | 主题 |

## 不应交付 / 勿打包

- `.env`、任何真实 API Key / OSS Key  
- `output/` 内含运行日志与可能含业务字段的 JSON（本地验收用；若打包需二次审查）  
- `.venv/`、`__pycache__/`、`.pytest_cache/`  
- 完整私有签名 URL、未脱敏日志  

## 建议交付方式

- Git 私有仓库链接，或  
- 源码 ZIP（排除上表「不应交付」项）  

推送/打包前再跑：`git status` / 打包清单人工核对。
