# 第一阶段缺失环境变量清单

> 环境、依赖、数据（向量库 / 知识图谱 / 插图）已全部就绪。
> **只差以下 3~4 个值**，填好后告诉我，我将继续启动服务和 Smoke Test。

## 必填（阻塞启动）

### 1. `gateway/.env` — 上游 LLM（回答生成用）

| 变量 | 当前值 | 说明 |
|------|--------|------|
| `UPSTREAM_1_BASE_URL` | `__FILL_ME__` | OpenAI 兼容的上游地址，如 `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `UPSTREAM_1_API_KEY` | `__FILL_ME__` | 上游 API Key（如 DashScope 的 `sk-xxx`） |
| `UPSTREAM_1_MODEL` | `__FILL_ME__` | 上游真实模型名（如 `qwen-max`、`qwen-plus`） |

> 注意：answer/chat 侧请求的模型别名是 `qwen3-max` 和 `qwen3.6-plus`，而 gateway 的
> litellm 模板目前只暴露 `mimo-v2.5-pro` 一个别名。你填好上游后，我需要在
> `gateway/litellm/config.template.yaml` 中**追加这两个别名**（纯配置修改，不动业务代码），
> 把它们都路由到 UPSTREAM_1。

### 2. `retrieval/.env` — DashScope（向量嵌入 + 重排序用）

| 变量 | 当前值 | 说明 |
|------|--------|------|
| `KAFU_LLM_API_KEY` | `__FILL_ME__` | **必须是阿里 DashScope 的 Key**。retrieval 直接调用 DashScope 原生 `multimodal-embedding`（`qwen3-vl-embedding`）和 `qwen3-rerank` 端点，不走 gateway，无法用其他厂商替代 |

> 若没有 DashScope Key：Dense 检索和 Rerank 会失败，系统会降级到纯 BM25
> （VALIDATION_REPORT 验证过该降级路径可用），Smoke Test 仍能跑通但检索质量下降。
> 请告诉我你希望"填 Key"还是"接受纯 BM25 降级"。

## 已自动填好（无需操作）

| 文件 | 变量 | 值 |
|------|------|-----|
| `gateway/.env` | `LITELLM_MASTER_KEY` | `sk-interx-local-master`（本地自定义） |
| `answer/.env`、`chat/.env` | `INTERX_GATEWAY_API_KEY` | 同上，已对齐 |
| `answer/.env`、`chat/.env` | `INTERX_GATEWAY_BASE_URL` | `http://127.0.0.1:4000` |
| `web/.env` | `INTERX_CHAT_API_BASE` / `TOKEN` | `http://127.0.0.1:8000` / `sk_local_dev` |
| `kg/.env` | 全部 | 图谱已离线重建，本阶段不再调用 LLM |
| `process/.env` | 全部 | 使用预计算向量，本阶段不需要 DashScope |
| `gateway/.env` | `SEMANTIC_CACHE_ENABLED` | `false`（最小跑通关闭语义缓存，避免多一个 Key 依赖） |
