# Cloudflare R2 + Worker 最小接入设计

状态：**设计已确认 · M1–M3 本地实现完成（待你部署 Cloudflare 后联调）**  
目标：在保留阿里云 OSS 的前提下，增加可切换的 `CloudflareR2WorkerProvider`，使招聘方指定 OCR API（`file=` HTTPS URL）能够稳定拉取私有临时文件，最终满足 PDF/PNG OCR 硬性要求。  
依据：OSS 签名 URL → OCR **504**；Cloudflare Tunnel 合成 PDF/PNG OCR **PASSED**（见 `docs/tunnel_ocr_probe_report.md`、`docs/ocr_gateway_diagnosis.md`）。

---

## A. 最小接入架构

### A.1 原则

- **只动文件访问层**：复用现有 `OcrClient`、`OcrService.recognize()`、`BillingPipeline`。
- **不改**：LangChain 单 Agent、DeepSeek、财务规则引擎、AR/AP、JSON Schema、Streamlit 业务页。
- **保留**：`AliyunOSSStorage` 完整可用；通过环境变量切换 Provider。
- **OCR 契约不变**：`POST https://gateway.pltplt.com/ai/process`，字段 `file` / `task=orderChange` / `callBack` / `taskType`；**不要求** OCR 网关携带自定义鉴权 Header。

### A.2 现有接口（已存在，保持不变）

```python
# billing_agent/services/oss_storage.py（现状）
class FileUrlProvider(Protocol):
    name: str
    def put_temporary(self, data: bytes, suffix: str, content_type: str) -> TempObject: ...
    def delete(self, key: str) -> None: ...

@dataclass(frozen=True)
class TempObject:
    key: str
    url: str          # 交给 OcrClient.process(file_url)
    expires_at: datetime
```

`OcrService` 流程保持：`put_temporary` → `client.process(url)` → `delete(key)`（成功/失败均尽量清理）。

### A.3 目标数据流

```text
本地 bytes (PDF/PNG/…)
        │
        ▼
CloudflareR2WorkerProvider.put_temporary()
        │  1) PUT  https://<worker>/admin/objects/<key>
        │     Header: Authorization: Bearer <UPLOAD_TOKEN>
        │     Body: raw bytes + Content-Type
        │  2) 本地用 HMAC_SECRET 计算短时签名
        │  3) 返回 TempObject.url =
        │     https://<worker>/o/<key>?exp=<unix>&sig=<hex>
        ▼
OcrClient.process(url)  →  OCR 网关 GET 上述 URL（仅 query，无自定义 Header）
        │
        ▼
Worker GET /o/<key>
        │  校验 exp / sig / key 绑定 / 前缀 / 大小 / Content-Type
        │  经 R2 Binding 读私有对象，原样流式返回（无 302）
        ▼
OCR 结构化 JSON → 现有 ocr_blocks / Agent / 规则引擎
        │
        ▼
Provider.delete(key)  →  DELETE /admin/objects/<key>
+ R2 生命周期规则兜底清理 ocr-tmp/
```

### A.4 Provider 选择

| `FILE_URL_PROVIDER` | 行为 |
|---------------------|------|
| `aliyun_oss`（默认，若仅配 OSS） | 现有 `AliyunOSSStorage` |
| `cloudflare_r2_worker` | 新 `CloudflareR2WorkerProvider` |
| 未配置且两边都缺 | `OcrService` → `NOT_CONFIGURED`（诚实降级，text_layer ≠ OCR success） |

工厂建议放在 `billing_agent/services/file_url_factory.py`（新建），由 `OcrService.from_settings` 调用；**禁止**在 Pipeline 内写分支业务逻辑。

### A.5 Worker 路由设计

| 方法 | 路径 | 鉴权 | 用途 |
|------|------|------|------|
| `PUT` | `/admin/objects/<key>` | `Authorization: Bearer UPLOAD_TOKEN` | Python 上传临时对象 |
| `DELETE` | `/admin/objects/<key>` | 同上 | OCR 后删除 |
| `GET` | `/o/<key>?exp=&sig=` | HMAC query（无 Header） | OCR / 本机校验下载 |
| 其他 | `*` | — | `404` |

约束：

- `<key>` 必须匹配允许前缀（默认 `ocr-tmp/`），禁止 `..`、绝对路径、非白名单后缀。
- `GET` **禁止**重定向到 R2 公共 URL；用 Binding `env.OCR_BUCKET.get(key)` 后直接 `Response(body, { headers })`。
- 响应头：`Content-Type`（上传时写入的元数据或按后缀推断）、`Cache-Control: no-store`、`Content-Length`。

### A.6 HMAC 令牌（绑定对象）

```text
message = f"{key}\n{exp}"          # key 为完整对象键；exp 为 Unix 秒
sig     = hex(HMAC_SHA256(HMAC_SECRET, message))
url     = https://<worker-host>/o/{urlencoded_key}?exp={exp}&sig={sig}
```

校验失败返回 `403`；`exp < now` 返回 `401` 或 `403`（实现时统一一种并写测试）。  
`exp - now` 默认 ≤ `URL_EXPIRE_SECONDS`（建议 1800，与现 OSS 一致）；Python 侧继续沿用 `SIGNED_URL_SAFETY_MARGIN`（60s）。

---

## B. 需要新增或修改的文件

### B.1 新增（实现阶段）

| 路径 | 职责 |
|------|------|
| `workers/ocr-file-proxy/src/index.ts`（或 `.js`） | Worker：admin 上传/删除 + HMAC GET |
| `workers/ocr-file-proxy/wrangler.toml` | R2 binding、密钥绑定、路由 |
| `workers/ocr-file-proxy/package.json` | 仅 Worker 构建依赖（可选） |
| `billing_agent/services/r2_worker_storage.py` | `CloudflareR2WorkerProvider` |
| `billing_agent/services/file_url_factory.py` | 按 env 创建 Provider |
| `billing_agent/services/hmac_url.py` | 共享 HMAC 签名/校验（Python；与 Worker 算法一致） |
| `tests/unit/test_r2_worker_provider.py` | HMAC、工厂、错误码（MockTransport） |
| `tests/unit/test_hmac_url.py` | 向量测试（与 Worker 固定向量对齐） |
| `scripts/r2_worker_acceptance.py` | 合成 PDF/PNG 联调验收（部署后） |
| `docs/r2_worker_deploy.md` | 控制台步骤 + wrangler 命令（实现时从本计划拆出操作版） |

### B.2 最小修改（实现阶段）

| 路径 | 改动 |
|------|------|
| `billing_agent/config.py` | 增加 `R2WorkerSettings` + `file_url_provider` |
| `.env.example` | 记录新变量（无真实密钥） |
| `billing_agent/services/ocr_service.py` | `from_settings` 改为调用 factory（约数行） |
| `billing_agent/ui/dashboard.py` 或 `labels` | 服务状态展示 Provider 名称（可选、非阻塞） |
| `README.md` / `docs/assumptions.md` | 记录 Provider 切换与联调结论 |
| `.gitignore` | 忽略 `.wrangler/`、Worker 本地 `.dev.vars` |

### B.3 明确不改

- `billing_agent/agents/**`
- `billing_agent/business/**`（规则 / AR·AP / matcher）
- `billing_agent/schemas.py` 交付 JSON 结构
- `OcrClient` 请求字段与 endpoint（除非修 bug）
- Streamlit 五页业务逻辑（最多加一行「当前存储：R2 Worker」状态）

---

## C. Cloudflare 控制台需要创建的资源

本轮**不创建**；联调前由你配置。建议清单：

| # | 资源 | 配置要点 |
|---|------|----------|
| 1 | Cloudflare 账号 | 免费计划即可启动 |
| 2 | **R2 Bucket** | 名称如 `shipping-ocr-tmp`；**不启用**公共访问 / 自定义公共域 |
| 3 | **R2 生命周期规则** | 前缀 `ocr-tmp/`，例如 **1 天**后删除（兜底） |
| 4 | **Worker** | 名称如 `ocr-file-proxy`；绑定 R2：`OCR_BUCKET` → 上表 Bucket |
| 5 | Worker **Secrets** | `UPLOAD_TOKEN`、`HMAC_SECRET`（强随机，≥32 字节） |
| 6 | Worker 路由 | `*.workers.dev` 子域即可（笔试足够）；可选自定义域 |
| 7 | （可选）R2 API Token | **仅当**改为「Python 直连 S3 API 上传」时需要；本设计默认走 Worker admin，**可不创建** S3 密钥 |

费用相关：保持免费额度内；不启用付费智能分层 / 额外企业功能，除非另行授权。

---

## D. 安全配置和密钥管理方案

### D.1 密钥清单

| 密钥 | 存放位置 | 用途 | 是否进 Git |
|------|----------|------|------------|
| `UPLOAD_TOKEN` | Worker Secret + 本地 `.env` | 保护 PUT/DELETE | 否 |
| `HMAC_SECRET` | Worker Secret + 本地 `.env` | 签发/校验下载 URL | 否 |
| 阿里云 OSS AK | 现有 `.env` | 回退 Provider | 否 |

生成建议（本地）：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### D.2 环境变量（草案）

```env
# provider: aliyun_oss | cloudflare_r2_worker
FILE_URL_PROVIDER=cloudflare_r2_worker

R2_WORKER_BASE_URL=https://ocr-file-proxy.<subdomain>.workers.dev
R2_WORKER_UPLOAD_TOKEN=
R2_WORKER_HMAC_SECRET=
R2_WORKER_KEY_PREFIX=ocr-tmp/
R2_WORKER_URL_EXPIRE_SECONDS=1800
R2_WORKER_MAX_UPLOAD_BYTES=20971520
```

OSS 变量保持不变；切换回 OSS 时设 `FILE_URL_PROVIDER=aliyun_oss`。

### D.3 访问控制细则

1. R2 Bucket：**私有**；无公共 bucket URL。  
2. 上传/删除：仅持有 `UPLOAD_TOKEN` 的后端；Worker 校验 `Authorization`。  
3. 下载：HMAC 绑定 **具体 key + exp**；缺参、错签、过期、前缀不符 → 拒绝。  
4. 后缀白名单：与现 OCR 一致 `.pdf/.png/.jpg/.jpeg/.tif/.tiff`。  
5. 大小上限：与 `LimitSettings.max_file_bytes` 对齐（默认 20MB）；Worker 与 Python 双重检查。  
6. 日志：只记 `key` 的 `short_hash`、状态码、耗时；**禁止**完整签名 URL、Secret、文件正文。  
7. 不依赖 OCR 自定义 Header（Tunnel 实测 OCR 使用普通 GET + query）。  

### D.4 威胁与缓解（摘要）

| 威胁 | 缓解 |
|------|------|
| 令牌 URL 泄露 | 短 TTL；OCR 后立即 DELETE；生命周期兜底 |
| 暴力猜 key | UUID 文件名 + HMAC；无列表接口 |
| Admin Token 泄露 | Secret 轮换；仅本机 `.env`；CI 不注入生产样例 |
| 路径穿越 | 规范化 key；拒绝 `..`；强制前缀 |
| 误开公共桶 | 部署检查清单显式确认 Public access = Off |

---

## E. 部署及验证步骤

### E.1 部署顺序（你配置 Cloudflare 后执行）

1. 创建私有 R2 Bucket + 生命周期。  
2. 创建 Worker，绑定 R2，写入 Secrets。  
3. `wrangler deploy`，记录 `R2_WORKER_BASE_URL`。  
4. 本地 `.env` 填入 Provider 与密钥；**不提交**。  
5. 跑单元测试（Mock）→ 再跑 `scripts/r2_worker_acceptance.py`（真实合成文件）。

### E.2 兼容性验证计划（合成优先）

使用**无客户数据**的合成文件；费用类合成件需带可被 `orderChange` 识别的字段（见 E.3）。

| # | 验证项 | 通过标准 |
|---|--------|----------|
| 1 | Python 上传 R2 | admin PUT 200；对象存在（可用 HEAD/GET 自测） |
| 2 | Worker 授权下载 | 合法 `exp/sig` → 200 + 正确 Content-Type |
| 3 | SHA256 一致 | 下载字节 == 上传字节 |
| 4 | OCR 访问 Worker URL | 调用后 OCR 成功或可解释失败；对比 Tunnel 基线 |
| 5 | OCR 识别合成费用 | **结构化字段**与合成稿一致（见 E.3），非仅 `success=true` |
| 6 | 令牌过期 | `exp` 过去 → 4xx；OCR 不得误报成功 |
| 7 | 未授权 | 无 sig / 错 sig / 无 Bearer 上传 → 4xx |
| 8 | OCR 后删除 | `delete(key)` 后 GET → 404；生命周期规则已配置 |

控制请求次数：每项 OCR 最多 **1～2 次**；失败先查 Worker/R2 日志，避免轰炸网关。

### E.3 「真正识别」判定标准（禁止形式主义）

`orderChange` 对随意 marker 文本可能不回显（Tunnel 已证实）。因此验收必须使用 **航运费用形态** 的合成件，例如：

**合成 PDF/PNG 固定内容（示例）：**

- 标题含 `DEBIT NOTE` 或 `INVOICE`
- `MBL: R2TESTMBL9911`
- 费用行：`HANDLING CHARGE  50.00`，币种行 `USD`
- 合计：`TOTAL 50.00`

**OCR 通过条件（须同时满足）：**

1. HTTP 200 且 `success === true` 且 `data.list` 为非空数组；**并且**  
2. 至少一项可核对，例如：  
   - `chargeList`（或等价字段）中存在金额 **50** / **50.00**；或  
   - `mblNumber`（或等价）包含 `R2TESTMBL9911`；或  
   - 原始响应 JSON 字符串包含上述唯一锚点；  
3. 访问侧：若 Worker 可记日志，确认对应该 key 的 GET；  
4. 故意错误签名的对照组 OCR **不得**成功读到同一内容。

若 OCR 对合成稿仍返回空业务字段：记录为「网关拉取成功但结构化抽取未覆盖该版式」，**不得**标为「PDF/PNG OCR 硬性要求已满足」；随后用更接近招聘方样式的合成件或（在授权后）样例再验。

### E.4 与招聘方样例

- 默认：**不上传**招聘方真实账单。  
- 仅在 `AUTHORIZE_OCR_UPLOAD=1` + 明确授权后，用 R2 Provider 跑 PNG/扫描件验收。

---

## F. 预计的代码改动量

| 类别 | 估计 |
|------|------|
| Worker 源码 + wrangler | ~150–250 行 |
| `CloudflareR2WorkerProvider` + HMAC 工具 | ~150–200 行 |
| factory + config + `.env.example` | ~40–80 行 |
| `ocr_service.from_settings` 接线 | **≤15 行** |
| 单元测试 | ~150–250 行 |
| 验收脚本 + 文档 | ~200–300 行 |
| **业务 / Agent / 规则 / Schema** | **0 行功能性改动** |

总体：**小改动增量**（约 0.5–1.5 人日实现 + 联调），非重构。

---

## G. 费用和数据安全风险

### G.1 费用（量级）

| 项 | 笔试规模预期 |
|----|----------------|
| Worker 请求 | 免费额度内通常足够（上传+OCR拉取+删除，个位数～几十次/天） |
| R2 存储 | `ocr-tmp` 短时对象，接近可忽略 |
| 出站到 OCR | R2/Worker 出站有免费额度；控制验收次数 |
| 风险 | 误配公共流量或循环重试导致超额 → 验收脚本限次 + 失败熔断 |

**不**启用付费加速/企业附加包，除非另行授权。

### G.2 数据安全风险

| 风险 | 等级 | 说明 / 缓解 |
|------|------|-------------|
| 临时 URL 被转发 | 中 | TTL + 用后即删 + 生命周期 |
| 密钥进仓库 | 高 | `.gitignore`；PR 扫描；Secret 仅 wrangler / `.env` |
| 客户样例外传 OCR | 高 | 现有授权门闩；合成优先 |
| Worker 误开放列表/遍历 | 中 | 无 list API；仅精确 key |
| 多租户串读 | 低 | key 含日期+UUID；HMAC 绑 key |
| 日志泄密 | 中 | `redact_url` / `short_hash` 规范沿用 |

合规表述：文件经 Cloudflare 边缘被招聘方 OCR 拉取；与 Tunnel 试验同级数据出境路径，需在 README「已知限制」中如实说明。

---

## H. 如何回退到原有 OSS 方案

1. `.env` 设置：`FILE_URL_PROVIDER=aliyun_oss`  
2. 确保原有 `OSS_*` 变量仍有效。  
3. 重启 Streamlit / CLI；Dashboard 存储状态应显示 `aliyun_oss`。  
4. 无需删 Worker/R2（可保留作对照）；也无需改业务代码。  
5. 回归：合成文件走 OSS 时预期仍可能 **OCR 504**（已知）；回退目的是恢复「原链路可运行 / 可演示 text_layer」，不是宣称 OSS OCR 已通。  
6. 紧急情况：若 R2 Provider 代码异常，可临时导出 `FILE_URL_PROVIDER=aliyun_oss` 或清空 R2 配置使 factory 回退；`OcrService` 在无 Provider 时保持 `NOT_CONFIGURED` 诚实行为。

---

## 附录 1 · 类职责草图（实现时对照）

```text
file_url_factory.create_file_url_provider(settings) -> FileUrlProvider | None
    ├── aliyun_oss            → AliyunOSSStorage
    └── cloudflare_r2_worker  → CloudflareR2WorkerProvider

CloudflareR2WorkerProvider
    name = "cloudflare_r2_worker"
    put_temporary(data, suffix, content_type) -> TempObject
        build_object_key(prefix, suffix)
        httpx.put(admin_url, content=data, headers={Authorization, Content-Type})
        url = sign_get_url(base, key, exp, secret)
        return TempObject(key, url, expires_at)
    delete(key) -> None
        httpx.delete(admin_url, headers={Authorization})
```

## 附录 2 · Worker 伪代码要点

```javascript
// GET /o/:key?exp&sig
assert prefix ok && suffix ok
assert hmac(key, exp) == sig && exp >= now
obj = await env.OCR_BUCKET.get(key)
if (!obj) return 404
return new Response(obj.body, {
  headers: {
    "Content-Type": obj.httpMetadata?.contentType || guess(key),
    "Cache-Control": "no-store",
  },
})
// 禁止 Response.redirect(r2PublicUrl)
```

## 附录 3 · 实现里程碑（待你完成 Cloudflare 配置后）

| 里程碑 | 内容 | 完成定义 |
|--------|------|----------|
| M1 | Worker + HMAC 本地/预发 | 本机 curl 上传/下载/过期/拒签用例通过 |
| M2 | Python Provider + factory | 单测通过；`FILE_URL_PROVIDER` 可切换 |
| M3 | 合成费用 PDF/PNG → OCR | E.3 字段级断言通过 |
| M4 | 文档与回退演练 | README + 一键切回 OSS 验证 |
| M5 | （授权后）招聘方 PNG | 真实样例 OCR；失败如实记录 |

---

## 本轮结论

- **A–H 设计已闭环**，可直接作为实现与 Cloudflare 配置清单。  
- **当前不部署、不改主链路代码。**  
- 你完成控制台资源与 Secrets 后，再进入 M1–M3 真实联调；以「结构化字段核对合成费用」为 OCR 硬性要求的验收尺，而不是 `success=true`  alone。
