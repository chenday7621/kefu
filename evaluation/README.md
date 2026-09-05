# InterX 第一阶段基线评测（Original Baseline）

对原始 InterX（temperature=0.1，未做任何回答/检索逻辑修改）跑 **350 题**双语基准
（zh 163 / en 187，早前 351 口径系表头误计，见 VALIDATION_REPORT §1），产出可复现的
Original Baseline。评测直接在进程内调用 `answer.pipeline.answer()`，chat API 只用于
端到端 Smoke（见 verify/phase1-smoke/）。

## 目录结构

```
evaluation/
├── README.md                  # 本文件
├── VALIDATION_REPORT.md       # 验证阶段报告：口径审计、行号验证、阈值论证、Smoke 结果
├── scripts/
│   ├── check_mapping.py       # 【诊断，只读】数据集审计 + 证据→chunk 匹配分数分布
│   ├── check_c2_lang.py       # 【诊断，只读】C2 行号通路按语言拆分
│   ├── build_gold.py          # 构建 gold 映射（三通路分阈值，见下）
│   ├── run_baseline.py        # 批量跑题（断点续跑 / --retry-errors / 异常落盘）
│   ├── compute_metrics.py     # 确定性指标（hit@k / Recall@k / MRR / doc / 图片 / 耗时）
│   └── run_judge.py           # 可选 LLM-as-Judge（默认不跑）
├── gold/
│   ├── gold.jsonl             # 每题 gold：docs / chunks(带通路与分数) / images / unmapped_refs
│   ├── gold_build_config.json # 阈值、覆盖率、gold.jsonl sha256（复现凭据）
│   └── match_samples.json     # 匹配分数分档样本（人工审查用）
└── results/<run>/
    ├── raw.jsonl              # 每题完整 QAResult + 排序检索命中(rank/score/分数拆解) + 耗时 + 异常
    ├── metrics.json           # 指标汇总（每块自带覆盖数 n）+ 逐题明细
    └── error_samples.jsonl
```

## 前置条件

- 三服务中只需 **gateway (:4000)** 在运行（answer 层经它调 LLM）；chat API 与 web 不需要：

  ```bash
  cd gateway && set -a && . ./.env && set +a
  .venv/bin/python scripts/render_config.py   # .env 变更后需要
  nohup .venv/bin/litellm --config litellm/config.yaml --host 127.0.0.1 --port 4000 > logs/litellm.log 2>&1 &
  ```

- `retrieval/.env` 的 DashScope Key 有效（Dense + Rerank；失效会静默降级纯 BM25，跑前跑后建议检查日志无 `fallback|403`）。
- 使用 **chat 的 venv** 运行 runner（已含 answer/retrieval/kg 全部传递依赖）。

## 运行步骤

```bash
cd ~/projects/InterX

# 1. 构建 gold 映射（数据集或阈值变化后重跑；输出确定性 + sha256）
python3 evaluation/scripts/build_gold.py

# 2. 跑评测（增量执行：输出文件里已有的 id 自动跳过）
chat/.venv/bin/python evaluation/scripts/run_baseline.py \
    --out evaluation/results/baseline/raw.jsonl \
    [--ids 71,84,230] [--limit 50] [--lang zh] [--retry-errors]

# 3. 计算指标（可在任意进度上重复运行）
python3 evaluation/scripts/compute_metrics.py \
    --raw evaluation/results/baseline/raw.jsonl \
    --gold evaluation/gold/gold.jsonl \
    --out evaluation/results/baseline/metrics.json \
    --errors-out evaluation/results/baseline/error_samples.jsonl

# 可选：LLM-as-Judge（默认不跑，待 50 题阶段确认后启用）
chat/.venv/bin/python evaluation/scripts/run_judge.py \
    --raw evaluation/results/baseline/raw.jsonl \
    --gold evaluation/gold/gold.jsonl \
    --out evaluation/results/baseline/judge.jsonl --limit 5
```

## Gold 映射口径（详细论证见 VALIDATION_REPORT §2–4）

| 通路 | 适用 | 计分 | 阈值 |
|---|---|---|---|
| C2 | en 行号型 ref（行号已验证可信） | 手册原文↔chunk 双向包含 | 0.8 |
| C1t | zh 原文摘录 ref | 证据⊂chunk 正向重合 | 0.6 |
| C1p | 转述型 ref（summary/note） | 同上 | 0.8 |

- **zh 行号已验证不可信，构建时从不使用**；未达阈值/跨语言/.jpg 的 ref 全部留档 `unmapped_refs`，不猜测。
- 覆盖率：chunk 级 235/350（zh 48% / en 84%）、图片-chunk 296/350、doc 级 328/350；14 题双无只参与 doc/答案级指标。

## 指标口径

- **chunk 级 hit@k（任一 gold 进前 k）/ Recall@k（gold 覆盖比例）/ MRR**：仅在 chunk 覆盖题上算，每块自带 n，**不伪造**。
- **图片-chunk 通道**：以"包含 gold 图片的 chunk"为正例的独立检索指标（阈值无关，交叉验证用）。
- **doc 路由 hit@1/5**、**答案图片 precision/recall/exact**、**`<PIC>` 一致性**、**耗时 mean/p50/p95**。
- 断点续跑安全：按 id 幂等追加；`--retry-errors` 重跑错误题，读取方按"同 id 取最后一条"去重。

## 基线约定

- 保持项目原始 **temperature=0.1**（answer 各层）作为 Original Baseline，记入 `BASELINE_MANIFEST.yaml`；未按改造流程文档改 0，属有意决定，后续如需 temperature=0 版本另起结果目录对比。
- Router 每题失败降级 RAG（上游推理模型空返回）是 Original Baseline 真实行为，不修复、只记录（VALIDATION_REPORT §6）。
- 大约耗时：单题 30–60s（首题冷启动 95s+），350 题全量约 5–6 小时。
