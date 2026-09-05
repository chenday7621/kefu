# 第二阶段改造验证报告（VLM 图片理解 + 问题拆解）

> 日期：2026-07-18 ｜ 基线参照：baseline50 / BASELINE_350_REPORT.md（git 9679bd2）
> 改造代码：answer/vision.py、answer/decompose.py、pipeline 多查询 RRF 合并、网关 qwen-vl-plus 别名
> 开关默认全关（`vlm.enabled: false` / `decompose.enabled: false`）＝基线行为

## 1. 回归验证（硬约束：关闭态 = 基线）— PASS

同 20 题（分层抽样 id 列表）双开关关闭重跑 vs baseline50 记录：

- 检索 chunk 序列逐题比对：**20/20 完全一致（diff=0）**
- phase-2 字段泄漏（sub_questions / vlm_extraction / retrieval_calls）：**0**
- 工具：`evaluation/scripts/compare_regress.py`

## 2. 改造 B（decompose）消融 — PASS

同 20 题开 `decompose.enabled: true`（配置 `answer/configs/ablation_decompose.yaml`）：

| 项 | 关闭 | 开启 |
|---|---|---|
| 触发率 | — | **1/20**（该题集以单一问题为主，低触发符合预期，无误拆） |
| 触发题 | — | q196「耳机有哪些类型，以及如何更换耳塞？」→ 拆出 2 个自包含子问题，拆解质量正确 |
| hit@1 / hit@5（gold 覆盖 n=10） | 0.50 / 0.70 | 0.50 / 0.70（逐题零回退） |
| wall mean | 68.8s | 64.8s（无显著增量） |

结论：按需拆解判断从严生效，简单题零误拆、零指标回退；复合题正确拆解并走多查询 RRF 合并（2 次检索调用被插桩完整记录）。分析工具：`evaluation/scripts/analyze_decompose_ablation.py`。

## 3. 改造 A（VLM）端到端 4 场景 — PASS

配置 `answer/configs/ablation_vlm.yaml`（vlm.enabled: true），脚本 `evaluation/scripts/test_vlm_e2e.py`，记录 `/tmp/vlm_e2e_results.jsonl`：

| 场景 | 结果 |
|---|---|
| s1 空气炸锅图+提示音问题 | 提取 product_category=空气炸锅 conf 0.95、部件/铃铛图标识别正确；答案命中滤网提示音操作 |
| s2 空调图+遥控器排查 | product_category=空调室内机 conf 0.95；答案给出完整排查步骤 |
| s3 **图文矛盾**（空调图+洗碗机问题） | 修复后达标：答案**开头**明确提示"图片显示的是空调室内机，但您咨询的是洗碗机……请确认是否发错图片"，随后仍回答文字问题 |
| s4 **降级**（VLM 模型名故意配错） | 网关 400 → understand_images 返回 None → 答案照常完整生成，问答链路零阻塞 |

s3 曾首测未达标（冲突指令埋在注入块末尾被忽略），修复方式：`VLMExtraction.to_prompt_block` 把"回答前必须核对图文一致性、不一致须在答案开头指出"前置到块首并写入图片产品类别。

## 4. 过程中发现并修复的环境问题

- **render_config.py 静默渲染空凭据**：env 未 source 时所有别名 api_key 渲染为空 → 网关全线 500。已加保护：env 缺失直接报错拒绝渲染。
- **milvus-lite 单进程锁**：两个评测/测试进程并行会抢 `manual_chunks.db` 锁，dense 通道静默降级（表现为检索质量下降）。**约束：任何评测不得与另一评测进程并行**；并发只能用 run_baseline 的进程内 `--workers`。

## 5. 遗留（下一步候选）

- 带图小评测集（10-15 题，`evaluation/gold/image_questions.jsonl`）尚未建——4 场景是冒烟级验证，量化 VLM 收益需要小集
- 复合题子集的 decompose 定向消融（20 题里只有 1 题复合，B 改造的收益量化不足）
- 网关配置快照与 350 基线的 config_snapshot 存在别名差异（新增 qwen-vl-plus）——不影响已有三别名路由，但复评基线时注意
- chat API 端到端（带图走 /chat 接口含临时文件生命周期）未单独测：answer 层内同步完成读图，风险低，可在 web 联调时顺带验证
