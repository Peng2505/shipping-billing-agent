> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# D. OCR 遗留问题报告

状态：**OPEN · 高优先级**  
分类：`OCR_GATEWAY_TIMEOUT_FETCHING_FILE`  
详细原始诊断：[`docs/ocr_gateway_diagnosis.md`](../ocr_gateway_diagnosis.md)（2026-10-30）

## 已证实（勿重复无意义轰炸网关）

| 检查 | 结果 |
|------|------|
| 真实 OSS put（私有 ACL） | PASSED |
| 签名 URL 本机 GET | PASSED（~2s，body SHA 一致） |
| 未签名对象 GET | 403 |
| OCR + **公开** PDF URL | PASSED（~12–20s） |
| OCR + **OSS 签名** URL | **FAILED HTTP 504** ~60–65s（nginx Gateway Time-out） |
| 临时对象删除 | PASSED |

结论：失败点在 **OCR 网关拉取 `file=` URL** 阶段，而非本地签名错误。诊断文档已含给服务方的英文排查说明。

## 本轮 Phase 5 策略

- **不**再对签名 URL 发起新一轮 OCR 压测（避免无意义外部请求）。
- 样例验收默认 `enable_ocr_upload=False`。
- UI 继续区分：仅配置地址 ≠ 已验证；text_layer ≠ OCR success。

## 禁止项（已遵守）

- 不把 Bucket 改为公共读  
- 不擅自开通付费传输加速  
- 不上传未经授权的招聘方真实业务文件到外网  

## 建议服务方排查

1. Worker 是否可出网访问 `*.aliyuncs.com`  
2. 是否支持带 query（Expires/Signature）的 HTTPS URL  
3. 拉取超时是否约 60s 被 nginx 切断  

## 对验收的影响（提交前必须如实）

| 项 | 验收状态 |
|----|----------|
| OSS 签名 URL → 指定 OCR API | **未通过**（HTTP 504） |
| 招聘方 PNG 真实 OCR | **未验证通过** |
| 招聘方 PDF/图片经指定 OCR 全链路 | **不得标为通过** |
| 公开 URL OCR + Client/OSS 本端 | 可写为已验证 |
| PDF text_layer 降级 | 可用，但 **≠ OCR success** |

PNG 费用提取在链路修复前保持 BLOCKED。不改 Bucket 公共读；不擅自上传真实客户/招聘方样例。
