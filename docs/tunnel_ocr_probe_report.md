# Cloudflare Tunnel → OCR 受控验证报告

- 时间（UTC）：2026-10-30T11:49Z  
- 原始产物：`output/tunnel_ocr_probe/latest_report.json`  
- 范围：仅实验性验证；**未**替换阿里云 OSS；**未**改业务规则 / LangChain / Streamlit  
- 文件：仅合成 PDF/PNG（含唯一 marker）；随机短时 token 路径；测试后 Tunnel 已关闭  

OCR 调用：`POST https://gateway.pltplt.com/ai/process`  
参数：`file` / `task=orderChange` / `callBack=""` / `taskType=""`  

---

## 1. Cloudflare Tunnel PDF 测试结果

| 步骤 | 结果 |
|------|------|
| A. 经 Tunnel HTTPS 下载合成 PDF | **PASSED**（200，SHA 一致，`%PDF`，~639 ms） |
| B. 指定 OCR 处理该 PDF | **PASSED**（HTTP 200，`success=true`，`data.list` 长度 1，~12.8 s） |

说明：`orderChange` 结构化结果未回显 PDF marker 原文（`TUNNEL-PDF-MARKER-A7F3`），属接口形态限制，不单独据此否定拉取。

## 2. Cloudflare Tunnel PNG 测试结果

| 步骤 | 结果 |
|------|------|
| C0. 经 Tunnel 下载合成 PNG | **PASSED**（200，SHA 一致） |
| C. 指定 OCR 处理该 PNG | **PASSED**（HTTP 200，`success=true`，`data.list` 长度 1，~7.1 s） |

PNG marker 同样未出现在结构化字段中；与 PDF 响应 **payload 不相等**（不同 `createDate` / 不同 payload hash）。

## 3. OCR 是否真正访问并读取了文件？

**是（有访问日志证据）。**

OCR 调用时间窗内，本地受控服务收到针对 **对应 token 路径** 的 GET：

| 文件 | OCR 窗内 GET 次数 | User-Agent | 状态 | 字节 |
|------|-------------------|------------|------|------|
| synth_probe.pdf | 2 | `Python-urllib/3.13` | 200 | 1004 |
| synth_probe.png | 2 | `Python-urllib/3.13` | 200 | 8185 |

- 客户端经 cloudflared 回源，日志中 `client=127.0.0.1`（预期）。  
- 本机探测使用 **httpx** UA；OCR 窗内为 **Python-urllib/3.13**，可与自测 GET 区分。  
- 仅开放 `/t/<token>/<filename>`；错误 token → 403；不暴露文件系统。  
- 不能把「仅 HTTP 200」当成功：已同时要求 `success=true` + `data.list` 为数组 + 访问日志命中。

## 4. 与阿里云 OSS 方案对照

| 项 | 阿里云 OSS 签名 URL | Cloudflare Quick Tunnel + 受控本地服务 |
|----|---------------------|----------------------------------------|
| 本机/签名侧下载 | PASSED | PASSED |
| 公开无 query PDF OCR | PASSED | （本测未重复） |
| 带 query 公开 PDF OCR | PASSED | — |
| 私有对象 / token 路径 → OCR | **FAILED HTTP 504 ~63s** | **PASSED ~7–13s** |
| OCR 侧拉取证据 | 无（网关 504） | 有（token 路径 GET ×2） |
| Bucket 公共读 | 未改 | 不适用 |
| 付费加速 | 未开 | Quick Tunnel 免费临时 |

结论（证据级）：OCR 网关 **能够** 拉取 Cloudflare Tunnel 提供的 HTTPS URL；对 **阿里云 OSS 上海签名 URL** 路径仍失败。根因仍需服务方日志确认（出网/`*.aliyuncs.com` 等），但「任意 HTTPS 都拉不到」已被否定。

## 5. 是否有必要更换存储方式？

- **笔试硬性 OCR 全链路（本地文件 → 可达 URL → 指定 API）**：有必要引入 **OSS 之外的备选 FileUrlProvider**，否则签名 URL 504 会继续阻塞 PNG/扫描件。  
- **不建议**立刻废弃 OSS 代码：保留作对照与若服务方放行后的选项。  
- **不建议**把 Quick Tunnel 直接当生产托管（主机名每次变化、无 SLA、URL 泄露即短暂公网可达）。

## 6. 推荐的最小改动方案（先方案，不迁移）

保持现有 `FileUrlProvider` / `OcrService` 边界，仅扩展文件访问层：

1. **首选（部署友好）**：Cloudflare **R2（私有）+ Worker**  
   - Worker 校验短时 HMAC/JWT 后流式返回对象；  
   - OCR 只拿到 `https://<worker>/o/<id>?exp=&sig=`；  
   - 无 Bucket 公共读；费用可控（免费额度内通常够笔试）。  
2. **次选（自托管）**：具名 Cloudflare Tunnel → 本机/小 VPS 上同一套 token 文件服务（需常驻 `cloudflared` + 域名）。  
3. **实现原则**：  
   - 新增 `TunnelOrR2UrlProvider`，配置开关选择 `aliyun_oss` | `cf_r2_worker`；  
   - 默认仍可走 OSS；OCR 失败时不自动降级伪造成功；  
   - **不改** LangChain Agent、业务规则、AR/AP、JSON Schema、Streamlit 业务页。  

Quick Tunnel 仅保留为 **联调探针**（本目录脚本），不进主路径。

## 7. 隐私 / 安全 / 费用风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| URL 泄露 | Quick Tunnel URL + token 在隧道存活期内可被拉取 | 短 token、测完即关；生产用短时签名 |
| 数据出境 | 文件经 CF 边缘到 OCR 服务方 | 仅授权合成/已授权样例；审计开关不变 |
| 暴露面 | 错误实现可能挂载整盘 | 白名单路径 + token；禁止目录浏览 |
| 费用 | Quick Tunnel 免费；R2/Worker 有免费层，超限才计费 | 设生命周期与大小上限；不开发票类加速除非授权 |
| 合规 | 招聘方样例外发仍需显式授权 | 保持现有 `enable_ocr_upload` 门闩 |

## 8. 清理状态

- `cloudflared` 进程：已终止  
- 本地 HTTP 服务：已 shutdown  
- 业务代码 / OSS 配置：未替换  
- 证据保留在 `output/tunnel_ocr_probe/`（属 gitignore 的 output）  
