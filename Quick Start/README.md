# Quick Start（一键安装 / 启动 / 停止）

面向 Windows 与 macOS 的双击脚本。仓库根目录 = 本文件夹的上一级。

| 步骤 | Windows | macOS |
|------|---------|-------|
| 1. 安装 | 双击 `1_Install.bat` | 双击 `1_Install.command` |
| 2. 启动 | 双击 `2_Start.bat` | 双击 `2_Start.command` |
| 3. 停止 | 双击 `3_Stop.bat` | 双击 `3_Stop.command` |

## 1_Install 做什么

1. 创建 `.venv`（需本机已有 **Python 3.11+**）
2. `pip install -r requirements.txt`
3. 从 **Cloudflare 官方 GitHub Releases** 下载 `cloudflared` 到 `tools/`
4. 若无 `.env`，从 `.env.example` 复制一份

安装后请编辑项目根目录 `.env`，至少填写：

- `LLM_API_KEY`
- `LLM_MODEL` / `LLM_BASE_URL`（DeepSeek 示例见 `.env.example`）
- `FILE_URL_PROVIDER=local_tunnel`（默认已是）

**不要**提交 `.env`。不要用不明确来源的 `cloudflared` 替换官方下载文件。

## 2_Start 做什么

调用与笔试演示相同的编排：LocalTunnel（Quick Tunnel）+ Streamlit。

浏览器打开：http://localhost:8501

## macOS 首次提示

若双击 `.command` 提示无法打开：

```bash
chmod +x "Quick Start/"*.command
```

或在「系统设置 → 隐私与安全性」中允许运行。

## 说明

- Quick Tunnel **不是**生产托管；每次启动公网 URL 会变。
- 仅停止本项目会话中记录的进程，不会误杀其他 Python / cloudflared。
- 底层实现：`scripts/quick_start/install_env.py`、`scripts/demo/start_exam.py`、`scripts/demo/stop_exam.py`。
