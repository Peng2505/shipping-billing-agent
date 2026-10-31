# R2 + Worker 部署与端到端验收报告

- 时间：2026-10-30（本地 UTC+8 晚间）  
- Worker：`https://ocr-file-proxy.zijianpeng25.workers.dev`  
- Version ID：`7ad0d3e5-048c-44d1-af16-7835f48248d6`  
- 约束：未上传招聘方真实文件；未推送 GitHub；未打包  

---

## 1. 鉴权复核（部署前）

| 检查 | 结论 |
|------|------|
| PUT `/admin/objects/*` | 必须 `Authorization: Bearer UPLOAD_TOKEN` |
| DELETE `/admin/objects/*` | 同上 |
| GET `/o/*` | 必须校验 HMAC(`key\\nexp`) + 未过期；无自定义 Header |
| 其他路径 | `404`；`/health` 仅返回 JSON，不读 R2 |
| 无 R2 公共读 / 无 redirect 到公共 URL | 代码直接 `OCR_BUCKET.get` 流式返回 |

---

## 2. 部署

| 项 | 结果 |
|----|------|
| `npx wrangler deploy` | **成功**（更新现有 `ocr-file-proxy`，未新建 Worker） |
| R2 Binding | `OCR_BUCKET → shipping-ocr-tmp` |
| Secrets | 未改 toml；沿用控制台已有 `UPLOAD_TOKEN` / `HMAC_SECRET` |
| `/health` | **`{"ok":true}`** HTTP 200（不再是 Hello World） |

---

## 3. 安全实测（全部 PASSED）

脚本：`scripts/r2_worker_security_live.py` → `output/r2_worker_acceptance/security_live.json`

| 用例 | 结果 |
|------|------|
| 合法 Bearer 上传 | PASSED |
| 未授权上传 | PASSED HTTP 401 |
| 未授权删除 | PASSED HTTP 401 |
| 错误签名 GET | PASSED HTTP 403 |
| 过期签名 GET | PASSED HTTP 401 |
| 路径穿越 GET | PASSED HTTP 400 |
| 合法签名下载 + SHA256 一致 | PASSED |
| 删除后不可访问 | PASSED HTTP 404 |

---

## 4. OCR 联调（合成 PDF/PNG）

脚本：`scripts/r2_worker_acceptance.py`  
控制：公开 W3C PDF → OCR **PASSED** ~13s（网关本身可用）。

| 步骤 | PDF | PNG |
|------|-----|-----|
| 上传 R2 via Worker | PASSED | PASSED（经 OcrService） |
| Worker 签名下载 / SHA | PASSED | （服务内上传） |
| 过期/错签/未授权 | PASSED | — |
| **招聘方 OCR API** | **FAILED HTTP 504 ~61s** | **FAILED HTTP 504 ~61s** |
| 字段级费用断言 | **未执行到**（OCR 未成功） | **未执行到** |
| 删除临时对象 | PASSED | OcrService finally 删除 |

### Worker Tail 关键证据（单次 OCR 窗口）

OCR 调用期间 tail 仅见：

- 本机 `PUT`（上传）
- 本机 `GET` ×2（SHA 自检）
- 本机 `DELETE`（清理）

**未见 OCR 网关对 `/o/...` 的 GET。**  
因此本次 504 更符合「OCR 上游未能拉取 `*.workers.dev` URL」，而不是 R2/HMAC/鉴权错误，也不是本机客户端 300s 超时。

对照：此前 **Cloudflare Quick Tunnel（`*.trycloudflare.com`）** 合成 PDF/PNG OCR 曾 **PASSED**（见 `docs/tunnel_ocr_probe_report.md`）。

---

## 5. 全链路（LangChain → 规则 → JSON）

因 R2 Worker URL 的 OCR 未成功，**不能**声称「Streamlit 上传 PDF/PNG → 指定 OCR → Agent → 规则 → JSON」在 **R2 Worker 路径上**已端到端通过。

本地业务回归（不依赖此次 OCR）：

- `pytest tests/unit`：**158 passed**（`output/r2_worker_acceptance/pytest_unit_after_deploy.txt`）

---

## 6. 最终判定（你要的明确结论）

| 目标 | 是否真正通过 |
|------|----------------|
| R2 私有存储 + Worker HMAC 文件服务 | **通过** |
| 安全（未授权 / 错签 / 过期 / 删除） | **通过** |
| **PDF 经招聘方指定 OCR API（R2 Worker URL）** | **未通过**（504；Worker 无 OCR GET） |
| **PNG 经招聘方指定 OCR API（R2 Worker URL）** | **未通过**（同上） |
| 合成费用字段级提取 | **未通过**（阻塞于上项） |

---

## 7. 剩余问题与建议（停止盲目重试）

1. **向 OCR 服务方确认**：worker 是否可出网访问 `*.workers.dev` / Cloudflare；对照已成功的 `trycloudflare.com` 与失败的 `aliyuncs.com`、`workers.dev`。  
2. **可选下一跳（需你确认后再做）**：为 Worker 绑定**自定义域名**（非 workers.dev）再测 1 次 OCR；或临时用已验证可达的 Tunnel 作 OCR 文件面，R2 仍作存储。  
3. 在 OCR 拉取打通前，PNG/扫描件仍无法满足「必须走指定 OCR」的硬性要求；PDF 文本层降级可用但**不等于 OCR 成功**。

---

## 8. 实现文件清单（本轮相关）

- `workers/ocr-file-proxy/src/index.js` / `hmac.js` / `wrangler.toml`  
- `billing_agent/services/{hmac_url,r2_worker_storage,file_url_factory}.py`  
- `billing_agent/config.py` / `ocr_service.py`（factory 接线）  
- `scripts/r2_worker_security_live.py` / `scripts/r2_worker_acceptance.py`  
- `docs/r2_worker_deploy.md` / 本报告  

OSS Provider 保留；`FILE_URL_PROVIDER=cloudflare_r2_worker` 可切换回 `aliyun_oss`。
