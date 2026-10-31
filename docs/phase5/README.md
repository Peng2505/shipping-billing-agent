# Phase 5 交付报告索引

> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
>
> 阅读时请区分：
> - **OSS / R2** 路径调用招聘方 OCR 仍存在 **HTTP 504** 问题（当时与现在均未宣称打通）。
> - **LocalTunnel** 路径在后续验收中已成功打通真实 PDF/PNG OCR。
> - 招聘方 **ZIM PNG**：真实 OCR **费用金额**可通过；**币种**仍可能缺失 → `currency=null` + `PENDING_REVIEW`（见 README §16）。
>
> 下列 A–H 文档保留当时客观结果，**不回写篡改**；若与当前 README / `docs/exam_ocr_acceptance_matrix.md` 冲突，以后者为准。

| 文档 | 内容 |
|------|------|
| [A_final_acceptance.md](A_final_acceptance.md) | 最终功能验收（历史） |
| [B_sample_results.md](B_sample_results.md) | 真实样例对照（历史） |
| [C_automated_tests.md](C_automated_tests.md) | 自动化测试（历史） |
| [D_ocr_leftover.md](D_ocr_leftover.md) | OCR 遗留问题（历史） |
| [E_security_check.md](E_security_check.md) | 安全与敏感信息（历史） |
| [F_delivery_manifest.md](F_delivery_manifest.md) | 交付文件清单（历史） |
| [G_requirements_matrix.md](G_requirements_matrix.md) | 笔试达标矩阵（历史） |
| [H_risks_and_limits.md](H_risks_and_limits.md) | 风险与限制（历史） |

**当前优先阅读：** 仓库根 [`README.md`](../../README.md)、[`docs/exam_ocr_acceptance_matrix.md`](../exam_ocr_acceptance_matrix.md)。

运行产物（本地，默认不入库）：`output/phase5_*.txt`、`output/phase5_sample_acceptance.json`、`output/sample_*_result.json`。
