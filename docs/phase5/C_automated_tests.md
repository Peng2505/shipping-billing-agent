> **历史阶段性验收记录，最新状态请以 README、最终验收矩阵及最新测试报告为准。**
> 区分：OSS/R2→OCR 仍可能 504；LocalTunnel 路径后来已打通；ZIM PNG 金额可过、币种可能缺失→null+PENDING。
# C. 自动化测试报告

## 命令与结果

### 1) 默认全量（跳过真实外呼）

```text
pytest tests -q
→ 132 passed, 11 skipped
```

产物：`output/phase5_pytest_default.txt`

跳过原因为 `NOT_TESTED: real external call; run with --run-real`（OCR/OSS/LLM marker）。

### 2) 真实 LLM

```text
pytest tests/integration/test_real_llm_extraction.py --run-real -v
→ 5 passed in ~54s
```

| 用例 | 结果 |
|------|------|
| capability_probe | PASSED |
| pdf1_excludes_conditional | PASSED |
| pdf2_three_charges | PASSED |
| eml_hc_ambiguity | PASSED |
| png_blocked_without_ocr | PASSED |

产物：`output/phase5_real_llm.txt`

### 3) Phase 5 AppTest E2E

```text
pytest tests/integration/test_phase5_e2e_apptest.py --run-real -v
→ 1 passed in ~21s
```

上传真实 PDF2 → 点击开始 → session 中 ≥3 决策且 JSON 六字段块齐全。

产物：`output/phase5_e2e_apptest.txt`

### 4) 样例验收脚本

```text
python scripts/phase5_sample_acceptance.py
```

产物：`output/phase5_sample_acceptance.json` 及 `output/sample_*_result.json`

## 说明

- Mock OCR 仅出现在 `tests/unit`；不计入「真实 OCR 集成通过」。
- 未将 BLOCKED/FAILED 改写为 PASSED。
