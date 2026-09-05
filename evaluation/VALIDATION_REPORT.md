# InterX 基线评测 — 验证阶段报告

> 日期：2026-07-16 ｜ 阶段：Gold 映射验证 + 5 题 Smoke Test（未跑全量，未跑 LLM Judge）
> 结论：**评测链路全部验证通过，等待确认后进入 50 题阶段**

## 1. 数据集口径审计（纠正 351 → 350）

| 项 | 数值 | 说明 |
|---|---|---|
| 题目总数 | **350**（zh 163 + en 187） | 之前口径 351 系把 en-question.csv 表头行计入。全库唯一 ID，无重复 |
| 有标注答案的题 | 350/350 | per_question/*.json 与题目一一对应，无缺失无多余 |
| 有 gold 图片的题 | 296/350 | 图片 ID → chunk 映射 100% 成功（701/701） |
| 空标注答案 | 0 | — |

### evidence_refs 实际有 5 种混用格式（共 1825 条）

| 格式 | 数量 | 语言 | 特征 |
|---|---|---|---|
| dict `file`+`text` | 119 | 全 zh | 近逐字摘录 |
| dict `file/source`+`summary` | 458 | zh 435 / en 23 | 转述，无原文 |
| dict `file`+`note` | 42 | 全 en | 转述变体 |
| 裸字符串 `"路径.md:行号"` | 1108 | **全 en** | 只有行号，无文本 |
| 裸字符串自由笔记（无文件） | 87 | 全 en | 不可映射，仅记录 |
| dict-other | 11 | en | 无文本字段 |

早期脚本只认 `file`+`text`，曾误报"212 题无实质证据"；识别全部格式后实际为 **328/350 题有实质证据引用**（22 题例外全部是 en，且其中大多有 gold 图片兜底）。

## 2. 行号准确性验证（决定映射策略的关键）

用"ref 同时带 text 和 lines"的样本，将 text 与当前手册对应行段做 3-gram 重合度检验：

| 语言 | 准确(≥0.5) | 部分(0.2–0.5) | 失准(<0.2) | 结论 |
|---|---|---|---|---|
| zh | 26 | 28 | **244** | **zh 行号不可信，禁止按行号取证**（如 q100 标 290-292，实际内容在 303-306） |
| en | 13 | 3 | 0 | en 行号可信 |

en 的 1108 条 string-path ref（只有行号）恰好全部是 en → 行号通路可用；zh 无 string-path ref → 不受影响。`build_gold.py` 中硬编码 `zh_lines_policy: never`。

## 3. 匹配分数分布与阈值论证

对每条实质 ref 计算与目标手册全部 small chunk 的最佳 3-gram 重合度（未预设阈值）：

**C2 通路**（en 行号→手册原文→chunk，n=1103）：977 条（88.6%）= 1.0，强双峰。逐字通路本应≈1.0，0.5–0.8 尾巴经核查是证据跨 chunk 边界（最佳单 chunk 只覆盖一半文本）。
**C1 text**（zh 摘录，n≈111）：双峰，61 条 ≥0.9；人工核对 0.5–1.0 各档样本全部正确，0.4 档出现确认错配。
**C1 summary/note**（转述，n≈460）：宽峰 0.2–0.7，tie（最佳与次佳差<0.05）占比高；0.3–0.5 区间有确认错配（如 q83 的 0.417 匹到"等离子滤网"而正确目标是"空气滤网"）。

### 最终阈值（`gold_build_config.json` 固化）

| 通路 | 阈值 | 计分方式 | 依据 |
|---|---|---|---|
| C2 | **0.8** | 双向包含取 max（反向要求 chunk ≥15 ngram，防碎块混入） | 逐字标准不放宽；反向包含正确解决跨界证据，1102/1103 映射成功、仅 1 条真失败 |
| C1t | **0.6** | 正向（证据⊂chunk） | 0.5+ 档样本全对、0.4 档有错配，留 0.1 安全边际 |
| C1p | **0.8** | 正向 | 转述天然低分 + 错配/tie 集中在中低分段，只收"半引用"式标注；**未为提高映射率放宽**，359 条低分记录进 `unmapped_refs` |

不伪造原则：达不到阈值 / 跨语言（q204 英文 ref 对中文手册）/ .jpg ref / 行号不可解析，全部落 `unmapped_refs` 并带最佳分数，绝不猜测。

## 4. Gold 构建结果

文件：`evaluation/gold/gold.jsonl`（sha256 `d46212…c7f111c`，350 行）＋ `gold_build_config.json`（阈值/参数/覆盖率全量固化）。

| 覆盖维度 | 总体 | zh | en |
|---|---|---|---|
| chunk 级（检索指标可算） | **235/350 (67%)** | 78/163 (48%) | 157/187 (84%) |
| doc 级 | 328/350 | 163/163 | 165/187 |
| 图片级 | 296/350 | 149/163 | 147/187 |
| chunk+图片双无 | **14 题** | — | — |

ref 级映射：C2 1102 条、C1t 84 条、C1p 81 条通过；低于阈值 C1p 359 / C1t 27 / C2 1 条记录在案。

**含义**：chunk 级 Recall/MRR 只在 235 题上计算并必须同时报告覆盖率；zh 的 chunk 覆盖率偏低是标注方式（转述为主）决定的，用图片-chunk 通道（阈值无关、覆盖 296 题）和 doc 级指标（覆盖 328 题）补充交叉验证。

## 5. Smoke Test（5 题：zh 71/84/230，en 298/405，4 本手册）

全部成功，0 错误。逐项验证：

| 验证项 | 结果 |
|---|---|
| 完整 QAResult 序列化 | ✅ final/small/mid/big 答案、context、chunk_ids、recall_meta、改写 query 全捕获 |
| 检索 rank/score 捕获 | ✅ 拦截 `search_hierarchical`（不改 answer 代码），20 small + 5 mid + 3 big/题，含 rerank 分与 dense/bm25 分数拆解（`scores` 字段） |
| JSONL 序列化 | ✅ 每题 1 行，UTF-8 |
| 断点续跑 | ✅ 重复执行同命令 `done=5 pending=0` 直接退出 |
| 异常记录 | ✅ 实测停网关跑 q72：`error`+`traceback` 完整落盘、`qa_result=null`、检索结果仍保留（见 `results/errortest/`）；`--retry-errors` 可重试错误题，读取方按"同 id 取最后一条"去重 |
| 指标计算 | ✅ 见下 |

Smoke 指标（n=5，仅验证管道，无统计意义）：chunk hit@1/3/5 = 0.6/0.8/**1.0**，MRR 0.71；doc hit@1 = **5/5**；图片 precision 0.83 / recall 0.57；`<PIC>` 占位符与图片列表一致性 5/5；单题耗时 29–95s（首题含冷启动），均值 51.6s。

## 6. 已知问题与风险

1. **Router 每题必失败降级**：`Router failed, defaulting to RAG: Expecting value…`——路由 LLM 返回空 content（疑似 deepseek 推理模型 max_tokens 不足，与第一阶段网关问题同源）。对本评测集无正确性影响（全是手册题，RAG 即正确路径），但每题多一次失败调用的延迟。**属于 Original Baseline 的真实行为，按约定不修改，仅记录。**
2. `rerank_applied`/`rerank_score` 是代码残留字段（永远 False/None）；rerank 实际生效的标志是 `retrieval_source == "rerank"`，已实测确认 rerank 在工作。
3. 14 题 chunk+图片双无，这部分只能计入 doc 级与答案质量指标。
4. temperature 保持原项目 0.1（answer 各层）/0.7（内部改写），**未改为 0**，将作为 Original Baseline 记入 `BASELINE_MANIFEST.yaml`。
5. 351→350 口径修正需同步到所有历史文档引用。

## 7. 复现命令

见 `evaluation/README.md`。核心三步：`build_gold.py` → `run_baseline.py --out … [--ids/--limit/--lang]` → `compute_metrics.py`。

## 8. 下一步（待确认）

- [ ] 跑 50 题分层样本（zh/en 按比例、覆盖三条 gold 通路），预计 45–60 分钟
- [ ] 50 题通过后再确认全量 350 题（预计 5–6 小时）
- [ ] LLM Judge 仍未运行，待 50 题后决定
