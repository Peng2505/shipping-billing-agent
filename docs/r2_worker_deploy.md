# Cloudflare R2 + Worker 部署与联调说明

对应设计：[`r2_worker_integration_plan.md`](r2_worker_integration_plan.md)  
本地代码：`workers/ocr-file-proxy/`、`billing_agent/services/r2_worker_storage.py`

**本文件中的 cloud 操作需你在 Cloudflare 控制台 / 本机登录后执行；代理不会擅自部署或开通付费产品。**

---

## 0. 你需要确认后再执行的步骤

| # | 操作 | 谁执行 | 说明 |
|---|------|--------|------|
| 1 | Cloudflare 账号登录 | 你 | `npx wrangler login` 或 Dashboard |
| 2 | 创建私有 R2 Bucket `shipping-ocr-tmp` | 你 | **关闭**公共访问 |
| 3 | 配置 R2 生命周期（前缀 `ocr-tmp/`，建议 1 天删除） | 你 | 兜底清理 |
| 4 | 写入 Worker Secrets | 你 | `UPLOAD_TOKEN`、`HMAC_SECRET` |
| 5 | `wrangler deploy` | 你确认后 | 首次部署 |
| 6 | 把 `R2_WORKER_*` 写入本地 `.env` | 你 | 勿提交 Git |
| 7 | 跑 `scripts/r2_worker_acceptance.py` | 你确认后 | 含真实 OCR 调用（合成文件） |

---

## 1. 控制台：创建 R2

1. Cloudflare Dashboard → **R2** → Create bucket  
   - Name: `shipping-ocr-tmp`（须与 `workers/ocr-file-proxy/wrangler.toml` 中 `bucket_name` 一致；若改名请同步改 toml）  
2. Settings → **Public access: Off**（不要连自定义公共域）  
3. Settings → Object lifecycle rules  
   - Prefix: `ocr-tmp/`  
   - Abort/Delete after **1 day**（或等价最短）  

---

## 2. 生成本地密钥（勿提交）

```powershell
python -c "import secrets; print('UPLOAD_TOKEN=' + secrets.token_urlsafe(48)); print('HMAC_SECRET=' + secrets.token_urlsafe(48))"
```

两枚密钥稍后同时写入：**Worker Secrets** 与本地 `.env`（必须一致）。

---

## 3. 部署 Worker（需你确认）

```powershell
cd workers\ocr-file-proxy
npm install
npx wrangler login
npx wrangler secret put UPLOAD_TOKEN
npx wrangler secret put HMAC_SECRET
npx wrangler deploy
```

部署成功后记下形如：

`https://ocr-file-proxy.<subdomain>.workers.dev`

可选本地自检（不连 OCR）：

```powershell
npm test
npx wrangler dev
```

---

## 4. 本地 `.env`（示例）

```env
FILE_URL_PROVIDER=cloudflare_r2_worker
R2_WORKER_BASE_URL=https://ocr-file-proxy.<subdomain>.workers.dev
R2_WORKER_UPLOAD_TOKEN=<same as Worker UPLOAD_TOKEN>
R2_WORKER_HMAC_SECRET=<same as Worker HMAC_SECRET>
R2_WORKER_KEY_PREFIX=ocr-tmp/
R2_WORKER_URL_EXPIRE_SECONDS=1800
R2_WORKER_MAX_UPLOAD_BYTES=20971520
```

回退 OSS：

```env
FILE_URL_PROVIDER=aliyun_oss
# 保留原有 OSS_* 即可
```

---

## 5. 验收（合成费用文件 + 字段级断言）

```powershell
.\.venv\Scripts\python.exe scripts\r2_worker_acceptance.py
```

通过标准摘要：

1. 上传 PDF → Worker GET → SHA256 一致、无重定向  
2. 过期 / 错签 → 401/403  
3. 无 Bearer 上传 → 401/403  
4. OCR PDF：`success=true` **且** JSON 含 `R2TESTMBL9911` 和/或金额 `50`/`50.00`  
5. `OcrService` 跑 PNG 同样字段级断言  
6. 删除后对象不可再下载  

产物：`output/r2_worker_acceptance/latest_report.json`  

**禁止**上传招聘方真实客户文件。

---

## 6. Streamlit 全链路（部署验收通过后）

1. `.env` 指向 R2 Worker  
2. `streamlit run app.py`  
3. 工作台勾选 OCR 上传授权（仅合成/已授权文件）  
4. 上传合成 PDF/PNG → 确认文档中心出现 `ocr_api` 来源块 → 账单/JSON 页有合法输出  

---

## 7. 回退

`FILE_URL_PROVIDER=aliyun_oss` + 原 `OSS_*`，重启进程。无需删除 Worker（可保留对照）。  
已知：OSS 签名 URL 对招聘方 OCR 仍可能 504。
