# InterX Original Baseline — 350 题全量评测报告

> 日期：2026-07-17 ｜ 结果目录：`evaluation/results/baseline350/` ｜ git `9679bd2`（tag `phase1-baseline`）
> 配置：原始 InterX（temperature=0.1，Router/检索/回答逻辑未修改），gold sha256 `d46212…111c`，前 50 题复用 baseline50（配置逐项核对一致）

## 0. 指标可信度声明

- **Hit@1 语义已人工审计验证**：中文 12 题全量逐题复核（`evaluation/audits/zh_hit1_full12_audit.md`），程序 Hit@1 与人工语义判断 100% 一致，无 Gold 错配导致的假阴性。
- **Hit@5、MRR、Recall 可能因 Gold 欠覆盖而系统性偏低**：同一审计发现 12 题中 3 题（25%）存在 Gold 欠覆盖（正确证据 chunk 未进 gold 集）。这些指标是保守下界，不作横向对比结论的唯一依据。
- 指标只在 Gold 覆盖题上计算，n 逐项标注；覆盖率见 §1。

## 1. 执行与覆盖

| 项 | 值 |
|---|---|
| 总题数（350 口径见 VALIDATION_REPORT §1） | 350 |
| 成功 | 350 |
| 失败（含 error 记录，可单独重试） | 0 |
| Router 判为 general（跳过检索） | 0 |
| chunk Gold 可评题 | 235 |
| 图片 Gold 可评题 | 296 |
| doc Gold 可评题 | 328 |

## 2. 检索指标（Strict chunk Gold）

| 指标 | 总体 | zh | en |
|---|---|---|---|
| hit@1 | 0.62 (n=235) | 0.31 (n=78) | 0.78 (n=157) |
| hit@3 | 0.77 (n=235) | 0.50 (n=78) | 0.90 (n=157) |
| hit@5 | 0.84 (n=235) | 0.65 (n=78) | 0.93 (n=157) |
| mrr | 0.71 (n=235) | 0.45 (n=78) | 0.85 (n=157) |
| recall@1 | 0.09 (n=235) | 0.18 (n=78) | 0.05 (n=157) |
| recall@3 | 0.18 (n=235) | 0.34 (n=78) | 0.10 (n=157) |
| recall@5 | 0.26 (n=235) | 0.51 (n=78) | 0.13 (n=157) |

## 3. 辅助通道

| 指标 | 值 |
|---|---|
| doc hit@1 | 0.90 (n=328) |
| doc hit@5 | 0.98 (n=328) |
| 图片-chunk hit@5（阈值无关交叉验证） | 0.41 (n=296) |
| 图片-chunk MRR | 0.21 (n=296) |

## 4. 答案图片指标

| 指标 | 值 |
|---|---|
| 图片 recall | 0.48 (n=296) |
| 图片 precision | 0.57 (n=263) |
| 图片完全一致率 | 0.28 (n=296) |
| `<PIC>` 一致性 | 1.00 (n=350) |
| 平均答案长度 | 560.12 (n=350) |

## 5. 延迟

| p50 | p95 | mean |
|---|---|---|
| 43.0s | 113.8s | 65.4s |

## 6. Router（插桩观测，未修改）

| 项 | 值 |
|---|---|
| 调用 | 350 |
| 失败（全部为空返回，根因见 router_diagnosis.json：max_tokens=32 + 推理模型） | 242 |
| 失败但 fallback RAG 成功（非降级失败） | 242 |
| 判为 general | 0 |
| Router 耗时 p50/p95 | 1.46s / 2.23s |

## 7. 错误与重试

1 题失败，error/traceback 已保存于 raw.jsonl，重试命令见 README（--retry-errors）。失败题清单：193

## 8. 待人工审计清单

见 `evaluation/audits/BASELINE_350_pending_audits.md`（中文 Hit@1=0 共 54 题、中文 Hit@5=0 共 27 题、随机 zh/en 各 5 题，种子 20260716）。审计只读，Gold 未修改。
