# LocalTunnelProvider（Cloudflare Quick Tunnel）操作说明

**用途：** 笔试 / 开发演示——让招聘方 OCR API 拉取本机临时文件（已验证可达）。  
**不是**生产对象存储。URL 每次启动都会变化。

对照：

| Provider | OCR 实测 |
|----------|----------|
| `aliyun_oss` | 签名 URL → OCR **504** |
| `cloudflare_r2_worker` | Worker URL → OCR **504**（无 OCR GET） |
| `local_tunnel` | Quick Tunnel → OCR **曾成功**（见 tunnel 探针）；以本轮验收为准 |

---

## 前置

1. `tools/cloudflared.exe` 已存在（或自行下载同路径）。  
2. Python venv 已安装项目依赖。  
3. **不要**把 Quick Tunnel 当生产；关闭后旧 URL 立即失效。

---

## 一键启动（推荐，含 Streamlit）

```powershell
cd d:\shipping-billing-agent
.\scripts\demo\Start-ExamDemo.ps1
# 停止（仅本项目会话进程）：
.\scripts\demo\Stop-ExamDemo.ps1
```

## 仅启动网关 + Tunnel

```powershell
cd d:\shipping-billing-agent
.\.venv\Scripts\python.exe scripts\local_tunnel\start_gateway.py
```

成功时打印：

- `admin`: `http://127.0.0.1:8765`
- `public`: `https://….trycloudflare.com`
- 写入 `output/local_tunnel/status.json` 与 `env.snippet`

**保持该终端运行。**

检查：

```powershell
.\.venv\Scripts\python.exe scripts\local_tunnel\status.py
```

---

## 配置 `.env`

将 `output/local_tunnel/env.snippet` 中的值合并进 `.env`（或每次启动后更新）：

```env
FILE_URL_PROVIDER=local_tunnel
LOCAL_TUNNEL_ADMIN_BASE_URL=http://127.0.0.1:8765
LOCAL_TUNNEL_PUBLIC_BASE_URL=https://….trycloudflare.com
LOCAL_TUNNEL_ADMIN_TOKEN=…
```

`LocalTunnelProvider` 也会从 `status.json` 刷新 public URL，避免使用过期 Tunnel 地址。

OCR 上传授权在 Streamlit 中**默认关闭**；演示时需勾选「授权上传至 OSS/OCR」类开关（文案可能仍含 OSS，实际走当前 Provider）。

---

## 启动 Streamlit

另开终端：

```powershell
cd d:\shipping-billing-agent
.\.venv\Scripts\streamlit run app.py
```

上传**合成** PDF/PNG，勾选 OCR 授权后运行。

---

## 停止与清理

```powershell
# Ctrl+C 结束 start_gateway.py
# 或：
.\.venv\Scripts\python.exe scripts\local_tunnel\stop_gateway.py
```

会结束 cloudflared、删除 `status.json`，防止误用旧 HTTPS URL。

---

## 安全要点

- 文件服务只绑定 `127.0.0.1`。  
- 仅 `/t/<token>/<object_id>` 可读；无列表接口。  
- Admin PUT/DELETE 需 Bearer。  
- 错误/过期 token → 401/403。  
- OCR 完成后 Provider `delete`；网关后台清理过期对象。  

---

## 验收脚本

```powershell
.\.venv\Scripts\python.exe scripts\local_tunnel_ocr_acceptance.py
```

分层报告：Tunnel 拉取 / OCR 网关 / 字段提取 / Pipeline，互不合并为单一 PASSED。
