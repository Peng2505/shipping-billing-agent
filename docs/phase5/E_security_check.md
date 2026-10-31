> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# E. 安全与敏感信息检查结果

## .gitignore

- `.env` / `.env.*`（保留 `!.env.example`）已忽略  
- `output/*` 已忽略（保留 `.gitkeep` 若存在）  
- `.venv/`、密钥类扩展名已忽略  

## 仓库内扫描

对 `billing_agent/`、`tests/`、`scripts/`、`docs/`、`.streamlit/` 扫描可疑模式（`sk-`、AWS/阿里云 Key 形态、私钥头、`x-oss-signature=` 等）。

| 命中 | 说明 |
|------|------|
| `tests/unit/test_pipeline.py` 含字面量 `sk-` | **断言** `"sk-" not in blob`（防泄漏测试），非真实密钥 |

未在源码/文档中发现可提交的 AccessKey、完整签名 URL 或 `.env` 内容。

## 运行时

- 本机存在 `.env`（**不得提交**；项目目录当前无独立 git remote 交付前请再检）。  
- 诊断文档对签名 URL 已脱敏（`redacted`）。  
- OCR/样例外发需工作台勾选授权；默认关闭。  

## 依赖快照（节选）

见 Phase 5 运行环境：`langchain==1.4.7`、`streamlit==1.66.1`、`pydantic==2.14.2`、`PyMuPDF==1.27.2.3`、`oss2==2.19.1` 等（`pip freeze` 于验收当日）。
