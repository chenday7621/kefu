# InterX 第一阶段最小跑通报告

> 日期：2026-07-15 ｜ 环境：WSL2 Ubuntu（Linux 6.6.87.2-microsoft-standard-WSL2）
> 状态：**✅ 完成 — 三服务运行中，全功能检索（Dense+BM25+Rerank）下 3/3 Smoke Test 通过**（历史两轮记录见 §7-8）

## 1. 启动顺序确认（来自 README / VALIDATION_REPORT）

1. 安装依赖（7 个包各自独立 venv）
2. 解压 `data/build-artifacts.tar.gz` → `process/artifacts/`
3. `process/scripts/build_db.py` 构建 Milvus 向量库（用预计算向量，无外部 API）
4. 重建知识图谱（离线中间产物，无 LLM）
5. 解压手册插图、创建 agentic-rag 软链接
6. 配置各包 `.env`
7. 启动顺序：**gateway(:4000) → chat API(:8000) → web(:8501)**

## 2. 环境检查与遇到的问题

| 检查项 | 结果 | 处理 |
|--------|------|------|
| Python | 3.12.3（满足 3.11+） | — |
| pip / ensurepip / venv | ❌ 系统 Python 无 pip、无 ensurepip（缺 `python3.12-venv` 包） | 无 sudo 免密，改用 **uv** 管理 venv |
| uv 安装 | ❌ `astral.sh` 无法连接（超时） | 从 PyPI 清华镜像下载 `uv-0.11.28` wheel，解出二进制放入 `~/.local/bin/uv` |
| gcc / build-essential | 未安装 | 未阻塞——所有依赖均有预编译 wheel |
| redis-server | 未安装 | 不阻塞；gateway 语义缓存不可用（本阶段已主动关闭） |
| 网络 | pypi.org 慢、files.pythonhosted.org 下载失败（exit 18） | 统一改用 `https://pypi.tuna.tsinghua.edu.cn/simple` |

## 3. 执行的命令（关键步骤）

```bash
# uv 安装（astral.sh 被墙的替代方案）
curl -sL https://pypi.tuna.tsinghua.edu.cn/packages/.../uv-0.11.28-...-x86_64.whl -o /tmp/uv.whl
python3 -c "import zipfile; zipfile.ZipFile('/tmp/uv.whl').extractall('/tmp/uv_extract')"
cp /tmp/uv_extract/uv-0.11.28.data/scripts/uv ~/.local/bin/uv && chmod +x ~/.local/bin/uv

# 各包 venv + 依赖（使用清华镜像）
export PATH=$HOME/.local/bin:$PATH UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
for pkg in process retrieval kg answer chat gateway web; do
  cd $pkg && uv venv .venv --python /usr/bin/python3 \
    && uv pip install -r requirements.txt -p .venv/bin/python && cd ..
done

# 补装依赖（requirements.txt 未声明但运行必需，见 §4）
uv pip install -p process/.venv/bin/python milvus-lite
uv pip install -p retrieval/.venv/bin/python milvus-lite
uv pip install -p chat/.venv/bin/python "pymilvus>=2.4" milvus-lite "rank-bm25>=0.2" "jieba>=0.42" "kuzu>=0.5" "requests>=2.28"

# 解压构建产物 + 建库
mkdir -p process/artifacts && tar -xzf data/build-artifacts.tar.gz -C process/artifacts/
cd process && .venv/bin/python scripts/build_db.py && cd ..
# → Done: 7293 chunks ingested in 10.8s

# 重建知识图谱（离线，无 LLM）
cd kg
.venv/bin/python .agents/skills/kg-cold-start/scripts/write_graph.py build \
  --evidence state/evidence_mapped.json --graph-dir state/graph.db \
  --process-dir ../process/artifacts/manuals
# → Manuals: 39, Chunks upserted: 7215, CO_EVIDENCE edges: 19021
.venv/bin/python .agents/skills/kg-cold-start/scripts/write_graph.py enrich \
  --graph-dir state/graph.db --semantic state/semantic_edges.json
cd ..

# 解压插图（见 §4 zip 路径问题）+ 汇总到 answer/chat 期望的目录
# → process/data/插图/ 共 2631 张

# agentic-rag 软链接
cd agentic-rag && ln -s ../data/ch-manual ch-manual && ln -s ../data/en-manual en-manual && cd ..
```

## 4. 必要修改与偏差记录（均未改业务逻辑）

| # | 事项 | 说明 |
|---|------|------|
| 1 | **补装 `milvus-lite`** | `process`/`retrieval` 的 requirements.txt 只写了 `pymilvus>=2.4`，但代码用本地文件 URI 连 Milvus，需要 `milvus-lite`（pymilvus 新版不再捆绑）。报错：`milvus-lite is required for local database connections` |
| 2 | **chat venv 补装跨包依赖** | `chat/src/chat/pipeline.py` 通过 `sys.path` 直接导入 `answer`→`retrieval`→`kg` 的源码，但 chat/requirements.txt 未声明 pymilvus/jieba/rank-bm25/kuzu 等。已在 chat venv 内补齐 |
| 3 | **插图 zip 含路径穿越条目** | `插图.zip` 内文件名形如 `../../../data/ch-manual/插图/xxx.jpg`（且为 UTF-8 flag 缺失导致乱码目录）。直接按 README 的 `unzip -d` 会解到错误位置。改用 Python zipfile（`metadata_encoding='utf-8'` + 剥离路径只取 basename）解压到 `data/{ch,en}-manual/插图/`，并合并拷贝到代码期望的 `process/data/插图/` |
| 4 | **KG 图谱数据差异** | 离线重建结果 CO_EVIDENCE 边 19,021 条，VALIDATION_REPORT 记录为 48,508 条（完整版含更多 evidence 映射）。README 验证项 `39 个 .kuzu 文件` ✅ 通过，第一阶段够用 |
| 5 | **语义缓存关闭** | 本机无 redis-server 且不想引入额外 API Key，`SEMANTIC_CACHE_ENABLED=false`。不影响核心问答（VALIDATION_REPORT 确认缓存只是加速层） |

## 5. 数据就绪状态（复现检查清单）

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| `ls process/artifacts/manuals/ \| wc -l` | 40 | 40 | ✅ |
| `ls process/artifacts/manual_chunks.db/collections/` | manual_chunks | manual_chunks | ✅ |
| 向量库 chunk 数 | — | 7,293 | ✅ |
| `ls kg/state/graph.db/*.kuzu \| wc -l` | 39 | 39 | ✅ |
| 插图文件 | — | 2,631 张（process/data/插图/） | ✅ |
| 各包依赖导入测试 | ok | 7/7 包全部通过 | ✅ |

## 6. .env 配置状态

已为全部 7 个包生成 `.env`。内部互联密钥（gateway master key ↔ answer/chat 的 gateway key ↔ web 的 chat token）已自动对齐填好。

**缺失且必须由用户提供的值**（已由用户填写，详见 [MISSING_ENV_VARS.md](MISSING_ENV_VARS.md)）：

1. `gateway/.env`：`UPSTREAM_1_BASE_URL` / `UPSTREAM_1_API_KEY` / `UPSTREAM_1_MODEL` — 上游 LLM，回答生成必需
2. `retrieval/.env`：`KAFU_LLM_API_KEY` — DashScope Key（Dense 检索 + Rerank）；不填则自动降级纯 BM25

**待用户填 Key 后需做的一处配置修改**（已在清单中说明）：
`gateway/litellm/config.template.yaml` 目前只暴露 `mimo-v2.5-pro` 别名，而 answer/chat 请求 `qwen3-max` / `qwen3.6-plus`，需追加这两个模型别名路由到 UPSTREAM_1（纯网关配置，不动业务代码）。

## 7. 服务启动（用户填写 Key 后恢复执行）

用户提供：`UPSTREAM_1 = DashScope compatible-mode / deepseek-v4-flash`，retrieval 使用同一 DashScope Key。

### 启动前的配置修改

| # | 文件 | 修改 | 性质 |
|---|------|------|------|
| 6 | `gateway/.env` | 删除模板残留的 3 行 `__FILL_ME__` 占位（dotenv 后值覆盖前值，会盖掉用户填的真实值） | 配置清理 |
| 7 | `gateway/litellm/config.template.yaml` | 追加 `qwen3-max`、`qwen3.6-plus` 两个模型别名（answer/chat 请求的名字），均路由到 UPSTREAM_1 | 网关配置，未动业务代码 |

### 启动命令与结果

```bash
# 1. gateway（start_local.sh 因 sh/bash pipefail 兼容问题无法直接跑，手动执行等价步骤）
cd gateway && set -a && . ./.env && set +a
.venv/bin/python scripts/render_config.py
nohup .venv/bin/litellm --config litellm/config.yaml --host 127.0.0.1 --port 4000 > logs/litellm.log 2>&1 &

# 2. chat API（README 的 `uvicorn src.chat.api:app` 会因包内绝对导入失败，需 PYTHONPATH=src）
cd chat && PYTHONPATH=src nohup .venv/bin/python -m uvicorn chat.api:app \
  --host 127.0.0.1 --port 8000 > /tmp/chat_api.log 2>&1 &

# 3. web
cd web && nohup .venv/bin/streamlit run app.py --server.port 8501 --server.headless true &
```

| 服务 | 端口 | 健康检查 | 结果 |
|------|------|---------|------|
| gateway (litellm) | 4000 | `GET /health`（带 master key） | ✅ 200，healthy_endpoints 含 deepseek-v4-flash |
| gateway 模型别名 | — | `qwen3-max` / `qwen3.6-plus` chat completion | ✅ 均正常返回 |
| chat API | 8000 | `GET /health` | ✅ `{"status":"ok"}` |
| web (Streamlit) | 8501 | `GET /` | ✅ 200，浏览器打开 `http://127.0.0.1:8501` |

### 检索降级插曲（第一轮，已解决）

第一轮 Smoke Test 时 DashScope 嵌入端点返回 **403 AllocationQuota.FreeTierOnly**（免费额度耗尽），系统按设计自动降级为纯 BM25（`allow_dense_fallback: true`，VALIDATION_REPORT 验证过的路径），第一轮 3 条测试在降级模式下通过。

用户随后在 DashScope 控制台**关闭"仅免费额度"模式**，期间产生两次配置波折（均已解决）：

| 问题 | 现象 | 根因与解决 |
|------|------|-----------|
| 嵌入 404 | `Embedding API failed: 404` | 用户将 `retrieval/.env` 的 base URL 改成 `.../api/v1`，而 [dense.py](retrieval/src/retrieval/dense.py) 会剥掉末尾 `/v1` 再拼原生路径，产生 `/api/api/v1/...` 双重路径。**改回 `.../compatible-mode/v1` 即恢复**（该值是代码约定的格式，dense/rerank 都会自动转换成原生端点） |
| gateway 上游 404 | `litellm.NotFoundError ... 404` | 用户将 gateway 上游换成阿里云专属推理端点 `ws-*.cn-beijing.maas.aliyuncs.com/api/v1`，该端点不响应 litellm 拼出的 `/chat/completions` 路径。**回退到公共 DashScope `compatible-mode/v1` + 原 Key**（第一轮实测可用组合）；ws- 专属端点配置在 `gateway/.env` 中注释保留，若要启用需向阿里云确认其 OpenAI 兼容调用地址 |

解决后验证：`smoke_dense.py` 输出 `embedding OK, dim: 1024` ✅；重启 gateway + chat API 后 Dense+Rerank 全功能生效。

### 配置速查：两个 .env 各管什么

| 文件 | 用途 | 模型 | 注意 |
|------|------|------|------|
| `gateway/.env` `UPSTREAM_1_*` | 对话生成（answer/chat/kg 全部经 litellm :4000） | `deepseek-v4-flash`（`qwen3-max`/`qwen3.6-plus` 均为别名） | 改后需重启 gateway（配置在启动时渲染） |
| `retrieval/.env` `KAFU_LLM_*` | 检索（不经网关，直连 DashScope 原生 API） | `qwen3-vl-embedding`（嵌入）+ `qwen3-rerank`（重排） | base URL 必须是 `https://dashscope.aliyuncs.com/compatible-mode/v1`；Key 必须是普通 DashScope Key（`sk-` 开头，非 `sk-ws-`）。改后需重启 chat API |

**能否更换嵌入/重排序模型**：嵌入模型不可轻易换——Milvus 里 40 本手册的向量是 `qwen3-vl-embedding`（1024 维）预计算的，换模型需重嵌全部 chunk 并重建向量库；重排序可换——改 [retrieval/configs/default.yaml](retrieval/configs/default.yaml) 的 `rerank.model_name`，或置 `rerank.enabled: false` 退回 RRF 融合排序。

## 8. Smoke Test（两轮均 3/3 通过）

### 第一轮：BM25 降级模式（嵌入 403 期间）

| # | 问题 | 类型 | 耗时 | 回答长度 | 图片 | 结果 |
|---|------|------|------|---------|------|------|
| 1 | 空调制冷效果不太好怎么办？ | 中文手册 | 60.6s | 416 字 | 1（Manual17_39） | ✅ |
| 2 | How do I use the air fryer for the first time? | 英文手册 | 38.4s | 939 字符 | 3（Manual08_5/6, air_fryer_01） | ✅ |
| 3 | 滤网在哪里？怎么拆下来清洗？（复用 #1 会话） | **多轮指代消解** | 36.7s | 335 字 | 2（Manual01_31/32） | ✅ |

### 第二轮：全功能检索（Dense + BM25 + Rerank，最终状态）

测试脚本：[verify/phase1-smoke/run_smoke.py](verify/phase1-smoke/run_smoke.py)

| # | 问题 | 耗时 | 回答长度 | 图片 | 结果 |
|---|------|------|---------|------|------|
| 1 | 空调制冷效果不太好怎么办？ | 224.4s | 460 字 | 3（Manual01_7/33/34） | ✅ |
| 2 | How do I use the air fryer for the first time? | 51.8s | 804 字符 | 3（Manual08_5/6, air_fryer_01） | ✅ |
| 3 | 滤网在哪里？怎么拆下来清洗？（复用 #1 会话） | 48.2s | 275 字 | 2（Manual01_29/30） | ✅ |

- `grep -ci "fallback|403" /tmp/chat_api.log` = **0**——全程无降级，Dense+Rerank 实际生效
- Dense 生效后 #1 图片引用从 1 张增加到 3 张（滤网清洁、极速键操作步骤图），且图片来源手册（Manual01）与 #3 多轮追问一致，检索聚焦度优于纯 BM25 轮次
- #1 耗时 224s 明显偏长：该轮为 gateway/chat 重启后首个请求，包含 jieba 词典重建、Milvus/KG 冷加载与上游推理模型（deepseek-v4-flash 带 reasoning）首调开销；#2/#3 回落到 ~50s 正常水平
- **#3 指代消解成功**——"滤网"正确解析为空调滤网，并给出 40°C 水温上限等手册细节；`<PIC>` 数量与 image_ids 严格一致
- 图片端点验证：`GET /images/Manual01_31` 返回 200，真实 JPEG（24.7KB）

## 9. 当前运行状态

```
gateway  : litellm  pid 见 gateway/state/litellm.pid   127.0.0.1:4000
chat API : uvicorn  日志 /tmp/chat_api.log              127.0.0.1:8000
web      : streamlit 日志 /tmp/web.log                  0.0.0.0:8501
```

停止方式：`kill $(cat gateway/state/litellm.pid)`；chat/web 用 `pkill -f "uvicorn chat.api"`、`pkill -f "streamlit run app.py"`。

## 10. 遗留事项

- **ws- 专属推理端点未接入**：用户购买的 `ws-kmwh0oag8ltzuhnf.cn-beijing.maas.aliyuncs.com` 专属端点对 `/api/v1/chat/completions` 返回 404，正确的 OpenAI 兼容调用地址待向阿里云控制台确认后再切换（配置已注释保留在 `gateway/.env`）
- 语义缓存保持关闭（无 redis-server）；KG 图谱为离线重建版（CO_EVIDENCE 边 19,021 条 vs 完整版 48,508 条）

## 11. 范围说明

按要求**未做**：LangGraph 改造、多模态改造、任何核心业务逻辑修改。
所有修改仅限：`.env` 生成与修正、gateway litellm 模板追加模型别名、venv 依赖补装、数据解压、验证脚本（`retrieval/scripts/smoke_dense.py`、`verify/phase1-smoke/run_smoke.py`）、独立评测工具包 `evaluation/`（只读调用业务代码）。
350 题基线评测已于 2026-07-17 完成：`evaluation/BASELINE_350_REPORT.md`。

## 12. 需要重点理解（改造流程文档第一阶段验收项，逐条回答）

### 12.1 用户问题从哪个入口进入

```
浏览器 → web/app.py (Streamlit :8501)
  → HTTP POST /chat（chat/src/chat/api.py:104 chat_endpoint，Bearer token 校验）
    → chat.pipeline.chat()（chat/src/chat/pipeline.py:24，会话/改写层）
      → answer.pipeline.answer()（answer/src/answer/pipeline.py:216，核心问答）
```

用户上传图片以 base64 data URL 进入，在 API 边界落成临时文件路径（api.py:79 `_parse_images`）后向下传递。基线评测入口（`evaluation/scripts/run_baseline.py`）直接调用 `answer()`，绕过会话层——对单轮独立问题两条路径等价（无历史时改写短路返回原句）。

### 12.2 查询改写和路由在哪里执行

**两处改写、一处路由**：

1. **会话层改写**（chat/src/chat/query_rewrite.py:8）：有历史时用 LLM 把当前问题改写成独立完整问题（如"滤网在哪里？"→"空调的滤网在哪里？"）；无历史或关闭时原样返回。这是唯一影响下游输入的改写。
2. **answer 层改写**（answer/src/answer/query_rewrite.py）：生成多个改写**但只写入 `recall_meta.rewritten_queries` 元数据，检索仍用原问题**（answer/pipeline.py:273-275 注释：预留给未来多查询召回）。
3. **路由**（answer/src/answer/router.py:14 `route_question`）：LLM 二分类 manual/general；带图问题直接 RAG；失败保守回退 RAG。350 题实测：242/350 次路由调用失败（全部为空返回），但 100% fallback 到 RAG，本题库全为手册题，路由结果无一错误。根因已诊断（`evaluation/results/baseline50/router_diagnosis.json`）：`max_tokens=32` 撞上推理模型 deepseek-v4-flash，reasoning 耗尽 token 后 content 为空（finish_reason=length）；max_tokens=256 即恢复。属 Original Baseline 真实行为，按约定未修。

### 12.3 Dense、BM25、Rerank 如何组合

```
问题 ──┬─ Dense：qwen3-vl-embedding(1024 维) 直连 DashScope 原生 API → Milvus(milvus-lite) top-20
       └─ BM25：jieba 分词 + rank-bm25 → top-20
              ↓
   加权 RRF 融合（retrieval/fusion.py:8 rrf_fuse）
   rank-based：score = Σ weight_ch / (rrf_k + rank)，权重 dense 0.65 / bm25 0.35
              ↓
   qwen3-rerank 二阶段重排（retriever.py:161，候选 rerank_candidate_k=20，可配置关闭退回 RRF 排序）
              ↓ top_k 小块命中
```

RRF 刻意用排名而非分数融合（两通道分数分布不可比）。降级链：嵌入 API 不可用时 `allow_dense_fallback: true` 自动退纯 BM25（第一轮 Smoke 已实测）。

### 12.4 多粒度检索和答案融合如何实现

- **构建期**（process 包）：手册切成 big→mid→small 三级层级 chunk，small 为嵌入/检索锚点，chunk_id 编码层级关系（`{doc}_small_XXXX_YYYY_ZZZZ` ↔ mid/big 前缀）。
- **检索期**：`search_hierarchical`（retrieval/retriever.py）以 small 命中为基础，回溯聚合出 mid/big 层命中（MidHit.small_hits 记录子命中）。
- **生成期**（answer/pipeline.py:371-408）：small/mid/big 三路**并行**生成答案（ThreadPoolExecutor(3)，各自 prompt `small_answer.md`/`mid_answer.md`/`big_answer.md` 与上下文预算）→ `_ensemble_answer`（pipeline.py:145，`ensemble.md`）把三路答案融合成最终回答——精确事实、操作步骤、背景上下文各取所长。

### 12.5 图片 ID 如何从文档传递到最终答案

```
手册 markdown ![图示](插图/Manual06_13.jpg)
→ process 切块时存入 chunk.image_paths / image_abs_paths
→ 检索命中随 SearchHit 携带
→ answer/images.py collect_image_evidences：命中 chunk 的图片 → ImageEvidence（image_id=文件名 stem）
→ 图片清单(manifest)+图片本体作为视觉输入进 LLM prompt
→ LLM 输出 content 含 <PIC> 占位符 + images 数组（JSON 契约）
→ answer/normalizer.py 校验：images ⊆ 允许集合、<PIC> 数与 images 数一致
→ chat API GET /images/{image_id}（api.py:133）从 process/data/插图/ 回源文件
→ web 端按序把 <PIC> 替换为图片渲染
```

350 题实测 `<PIC>` 占位符一致性 350/350 = 100%。

### 12.6 多轮记忆如何保存和压缩

- **保存**（chat/src/chat/store.py）：会话为 JSON 文件，按 `session_dir/{user_id}/{session_id}.json` 持久化，每轮存 Turn（用户消息/助手消息/图片 ID/改写后查询）。
- **压缩**（chat/src/chat/memory.py）：`get_context_for_query` = 滑动窗口（最近 `window_size=5` 轮原文）+ 历史摘要；超过 `summary_trigger_turns=10` 轮后 `maybe_update_summary` 用 LLM 把老轮次压缩进 summary（temperature 0.3）。
- **用途边界**：历史只用于改写当前问题（12.2），answer 层完全无状态。

### 12.7 LiteLLM 网关是否为核心流程所必需

**部署上当前必经，架构上可替换。** 生成侧全部 LLM 调用（answer 三粒度+ensemble+router、chat 改写/摘要、kg 构建）经 `.env` 指向 :4000 网关，三个模型别名（qwen3-max/qwen3.6-plus/mimo-v2.5-pro）当前都路由到同一上游 deepseek-v4-flash；检索侧（嵌入/重排）**不经网关**，直连 DashScope 原生 API。把各包 `.env` 的 base_url 改指上游即可绕过网关，业务逻辑无感知——网关的价值是模型别名统一、多上游切换、（可选，本机关闭）语义缓存与统一可观测，而非功能必需。

### 12.8 KG 开启和关闭分别产生什么影响

- **开启**（answer/configs/default.yaml `kg.enabled`，当前基线为开）：检索完成后 `ChunkExpander`（kg/src/kg/expander.py）对 small 命中做图谱扩展——沿 CO_EVIDENCE/语义边找相邻证据 chunk，上限 `max_expanded`，以 `retrieval_source="kg_expand"` 追加到 small_hits 尾部参与答案生成（answer/pipeline.py:282-322）。任何失败**优雅降级**只记 warning（实测 Twin_Tub_Washing_Machine 无图谱文件，39/40 手册有图谱，相关题正常跳过扩展）。
- **关闭**：纯混合检索结果直接进入生成，无追加证据。
- **定量影响**：Phase 1 不下结论——需第四阶段消融（方案 A vs F）对比才能回答"KG 值不值"。本机图谱为离线重建版（CO_EVIDENCE 19,021 边 vs 完整版 48,508），结论会偏保守。

### 12.9 351 道题如何运行和计算指标

- **口径**：实际 **350 题**（zh 163 + en 187；en-question.csv 为 187 非文档所称 188，`evaluation/VALIDATION_REPORT.md` §1 已审计），350/350 全部有标注。
- **Gold 构建**（evaluation/scripts/build_gold.py）：evidence 标注实有 5 种格式，经三条通路映射到 chunk——C1t（中文逐字摘录，3-gram 重合≥0.6）、C1p（转述，≥0.8 严格阈值）、C2（英文 `文件:行号` → 取手册原文 → 双向包含≥0.8）；阈值由分数分布+人工样本审查确定，未强行放宽。chunk 级覆盖 235/350，图片级 296/350，doc 级 328/350；未映射项记录不伪造。
- **运行**（evaluation/scripts/run_350_pipeline.sh）：网关健康探针 → `run_baseline.py` 直调 `answer()`（进程内一次初始化、逐题写 JSONL、断点续跑、失败题可 `--retry-errors` 单独重试、Router/检索 rank/score 插桩捕获）→ `compute_metrics.py` → `make_350_report.py` 自动出报告与待审计清单。
- **指标**：Strict chunk Hit@1/3/5、MRR、Recall@k（仅在 Gold 覆盖题上计算并同时报告覆盖率）；doc Hit@1/5；图片-chunk 通道（阈值无关交叉验证）；答案图片 precision/recall/exact；延迟 p50/p95；Router 失败/fallback 统计。Hit@1 语义经 12 题人工全量审计验证；Hit@5/MRR/Recall 因 Gold 欠覆盖（审计发现约 25% 题存在）为保守下界。
- **350 全量结果**（2026-07-17，`evaluation/BASELINE_350_REPORT.md`）：350/350 成功 0 失败；chunk hit@1/3/5 = 0.62/0.77/0.84，MRR 0.71；doc hit@1 0.90 / hit@5 0.98；答案图片 recall 0.48 / precision 0.57；延迟 p50 43.0s / p95 113.8s；Router 失败 242/350（全部空返回→fallback RAG 成功，0 题走错路径）。


目前的链路：
用户问题 → [多轮才有]历史重写 → 路由 → dense∥bm25 → RRF融合 → rerank
→ [KG扩展] → 三粒度并行生成 → ensemble融合（此时已含图片ID+占位符）→ web按ID渲染图片
