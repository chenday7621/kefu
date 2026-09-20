# InterX Baseline V1 运行环境与复现说明

本文档描述 `baseline-v1-candidate` 的运行边界、已验证环境、依赖、外部服务、密钥配置和复现步骤。它只记录 Baseline V1 Foundation；不表示 Human Gold Verification、正式 DEV 或正式 HELDOUT 已完成。

## 1. 当前状态

| 项目 | 状态 |
| --- | --- |
| 数据集 | InterX-350 Silver Benchmark |
| Split | Train 243 / Dev 54 / Heldout 53 |
| Human-Verified Gold | 尚未完成 |
| 正式 DEV / HELDOUT | 禁止在 Gold 完成前运行 |
| KG | Baseline V1 默认关闭 |
| LiteLLM | 可选，Baseline V1 默认关闭 |
| Provider | DashScope OpenAI-compatible API，直连模式 |
| 已验证平台 | Windows WSL2 + Ubuntu 24.04 LTS |
| 原生 Windows | 依赖可解析，但完整运行尚未验证 |

权威运行协议见：

- `evaluation/configs/baseline_v1.yaml`
- `answer/configs/baseline_v1.yaml`
- `retrieval/configs/default.yaml`
- `requirements-baseline-v1.lock`
- `scripts/reproduce_baseline_v1.sh`

## 2. 已验证的主机环境

以下是创建本 Candidate 时实际使用并通过测试的环境：

| 项目 | 实际值 |
| --- | --- |
| Host | Windows + WSL2 |
| Linux | Ubuntu 24.04.4 LTS (Noble) |
| Kernel | `6.6.87.2-microsoft-standard-WSL2` |
| Architecture | `x86_64` |
| CPU | 8 logical CPUs available |
| RAM | 约 7.6 GiB |
| GPU | NVIDIA GeForce MX450；Baseline 不强制使用 GPU |
| System Python | 3.12.3 |
| Baseline venv Python | 3.12.8 |
| uv | 0.11.28 |
| pytest | 8.3.5 |
| Git LFS | 3.4.1 |
| Docker | 当前验证环境未安装；直连 Baseline 不依赖 Docker |
| 当前 checkout 大小 | 约 995 MiB，未包含所有未来结果文件 |

建议至少预留 5 GiB 磁盘空间，用于虚拟环境、Git LFS、运行时图片、Milvus Lite 数据库和评测输出。

## 3. Python 与依赖

`pyproject.toml` 要求：

```text
Python >= 3.12, < 3.13
```

不要使用 Python 3.11 或 3.13 生成正式 Baseline，因为这会偏离冻结环境。

主要直接依赖：

| Package | Version | 用途 |
| --- | ---: | --- |
| fastapi | 0.139.0 | Chat/API 服务 |
| uvicorn | 0.51.0 | ASGI Server |
| openai | 2.45.0 | OpenAI-compatible Provider Client |
| pydantic | 2.13.4 | Schema / Config Validation |
| pymilvus | 3.0.0 | Milvus Client |
| milvus-lite | 3.0 | 本地向量数据库 |
| faiss-cpu | 1.15.0 | Milvus Lite 间接依赖 |
| rank-bm25 | 0.2.2 | BM25 Retrieval |
| jieba | 0.42.1 | 中文分词 |
| kuzu | 0.11.3 | KG Storage；正式 V1 默认不启用 KG |
| markdown-it-py | 4.0.0 | Markdown Parsing |
| requests | 2.34.2 | HTTP Client |
| PyYAML | 6.0.3 | YAML Config |
| python-dotenv | 1.2.2 | `.env` Loading |
| pytest | 8.3.5 | Tests |
| httpx | 0.28.1 | API Tests |

完整传递依赖以 `requirements-baseline-v1.lock` 为准，不要将正式 Baseline 安装命令改成无版本约束的 `pip install -U ...`。

可选依赖：

```text
web:       streamlit==1.49.1
tokenizer: tiktoken==0.11.0
```

## 4. 模型与调用链

Baseline V1 固定配置：

| 阶段 | Model / Mode |
| --- | --- |
| Answer | `deepseek-v4-flash` |
| Query Rewrite | `deepseek-v4-flash`，只记录 metadata，不接入正式 Retrieval |
| Judge | `deepseek-v4-flash`；人工校准前只能标记 `UNVALIDATED_JUDGE_METRIC` |
| Embedding | `qwen3-vl-embedding`，dimension 1024 |
| Reranker | `qwen3-rerank` |
| Answer Provider | DashScope OpenAI-compatible direct mode |
| LiteLLM | disabled by default |
| KG | disabled by default |
| VLM | disabled by default |

正式协议还固定：

```text
query_workers = 1
concurrency = 1
warmup_ids = [241]
retrieval_reload_policy = startup_once
random_seed = 20260904
outlier_threshold = 300 seconds
outlier_policy = retain and report separately
```

## 5. Secret 与外部服务

严禁把真实 `.env`、API Key 或 Token 提交到 Git。

### 5.1 正式 Baseline Answer / Judge

从模板创建 `gateway/.env`：

```bash
cp gateway/.env.example gateway/.env
chmod 600 gateway/.env
```

正式直连模式至少需要：

```dotenv
UPSTREAM_1_BASE_URL=<DashScope OpenAI-compatible base URL>
UPSTREAM_1_API_KEY=<secret>
UPSTREAM_1_MODEL=deepseek-v4-flash
```

`UPSTREAM_1_RPM`、`UPSTREAM_1_TPM` 只在 Gateway/LiteLLM 路径使用；正式直连 Baseline 不要求启动 LiteLLM。

### 5.2 Embedding / Reranker

从模板创建 `retrieval/.env`：

```bash
cp retrieval/.env.example retrieval/.env
chmod 600 retrieval/.env
```

必须配置：

```dotenv
KAFU_LLM_API_KEY=<secret>
KAFU_LLM_BASE_URL=<DashScope service base URL>
```

如果要从原始文档重新构建 embedding，`process/.env` 使用同名变量。

### 5.3 可选 Chat/Web Demo

Chat API：

```dotenv
INTERX_GATEWAY_API_KEY=<secret>
INTERX_GATEWAY_BASE_URL=<OpenAI-compatible endpoint>
INTERX_CHAT_API_TOKEN=<random strong token>
```

Web：

```dotenv
INTERX_CHAT_API_BASE=http://127.0.0.1:8000
INTERX_CHAT_API_TOKEN=<same token as Chat API>
```

Bearer Token 必须与配置值真实比较；不要使用示例值公开部署。

## 6. Git LFS 与运行时资产

`.gitattributes` 为以下扩展名声明了 Git LFS：

```text
*.zip
*.tar.gz
```

当前 Candidate 的实际对象状态需要额外区分：

| 文件 | 当前存储方式 |
| --- | --- |
| `data/ch-manual/插图.zip` | Git LFS，约 142 MB |
| `data/en-manual/插图.zip` | Git LFS，约 142 MB |
| `data/build-artifacts.tar.gz` | 历史原因仍是普通 Git blob，约 69.9 MB |

GitHub 已接受 `build-artifacts.tar.gz`，但提示它超过建议的 50 MB。它仍低于 GitHub 的单文件硬限制；本轮没有为了整理历史而重写 Candidate 提交。后续若迁移该文件到 LFS，应作为独立的历史治理任务处理。

克隆后必须执行：

```bash
git lfs install
git lfs pull
```

提交的压缩资产包括 Chunk Artifact 和原始图片压缩包。运行时资产由以下脚本安全解压：

```bash
.venv-baseline-v1/bin/python evaluation/scripts/prepare_runtime_artifacts_v1.py
```

预期生成：

```text
process/artifacts/manuals/<manual_id>/small_chunks.jsonl
process/artifacts/manuals/<manual_id>/mid_chunks.jsonl
process/artifacts/manuals/<manual_id>/big_chunks.jsonl
process/data/插图/*
```

向量数据库：

```text
process/artifacts/manual_chunks.db
```

若数据库不存在，由 `process/scripts/build_db.py` 构建。Milvus Lite 数据库同一时间只允许一个进程持有写锁；出现 `DataDirLockedError` 时先关闭仍在使用该数据库的进程，不要删除数据库规避锁。

旧 `manifest.json` 中可能保留构建机器的绝对 `source_path`。运行和人工审核应以当前仓库相对路径、`doc_name`、`source_span` 为准，不能依赖旧绝对路径。

## 7. WSL2 / Linux 推荐安装步骤

### 7.1 前置条件

```text
Git
Git LFS
Python 3.12
uv 0.11.28
Bash
GNU coreutils（提供 timeout）
可访问 DashScope 的网络
```

### 7.2 克隆与切换分支

```bash
git clone https://github.com/chenday7621/kefu.git
cd kefu
git checkout baseline-v1-candidate
git lfs install
git lfs pull
```

### 7.3 创建环境并运行离线复现

```bash
INTERX_V1_PYTHON=python3.12 ./scripts/reproduce_baseline_v1.sh
```

脚本默认创建：

```text
.venv-baseline-v1/
```

默认只执行确定性数据准备、资产恢复、审计和测试，不运行正式 DEV/HELDOUT。

### 7.4 测试

```bash
.venv-baseline-v1/bin/python -m pytest -q
```

Candidate 提交前的结果：

```text
123 passed
21 skipped
```

跳过项为尚未构建的 KG 图数据库测试；Baseline V1 正式配置中 KG 默认关闭。

### 7.5 网络 Smoke

仅在 `.env` 已正确配置时执行：

```bash
INTERX_V1_SMOKE=1 ./scripts/reproduce_baseline_v1.sh
```

该路径会执行：

```text
network preflight
retrieval probe
provider probe
小规模 smoke evaluation
```

在 Human Gold Verification 完成前，不得设置 `INTERX_V1_FULL=1`，不得正式运行 DEV 或 HELDOUT。

## 8. 原生 Windows 状态

### 8.1 当前结论

```text
Windows dependency resolution: PASS
Windows full runtime smoke: NOT RUN
Windows formal reproducibility: NOT VERIFIED
```

使用 Python 3.12 对锁定依赖进行 Windows 平台解析时，全部 51 个包均可解析。`milvus-lite==3.0` 是 `py3-none-any` 包并包含 Windows `msvcrt` 文件锁分支。但这不等价于项目已经通过原生 Windows 端到端测试。

### 8.2 当前不能原样使用的部分

1. `scripts/reproduce_baseline_v1.sh` 是 Bash 脚本。
2. 脚本使用 Unix `timeout`、权限位和 Shell 语法。
3. `evaluation/scripts/check_secrets_v1.py` 使用 POSIX mode bits；NTFS/Windows ACL 需要独立实现。
4. Gateway 和 KG 的运维入口主要是 `.sh`。
5. 当前没有 `reproduce_baseline_v1.ps1`。
6. 原生 Windows 上尚未实际验证 Milvus Lite 数据库构建、重开、Dense Search 和并发锁。

### 8.3 实验性手动安装

下面仅用于兼容性验证，不能替代正式复现报告：

```powershell
git clone https://github.com/chenday7621/kefu.git C:\src\kefu
Set-Location C:\src\kefu
git checkout baseline-v1-candidate
git lfs install
git lfs pull

py -3.12 -m venv .venv-baseline-v1
.\.venv-baseline-v1\Scripts\Activate.ps1
python -m pip install uv==0.11.28
uv pip install --python .\.venv-baseline-v1\Scripts\python.exe -r requirements-baseline-v1.lock
uv pip install --python .\.venv-baseline-v1\Scripts\python.exe --no-build-isolation --no-deps -e .

python evaluation\scripts\prepare_runtime_artifacts_v1.py
python process\scripts\build_db.py
python -m pytest -q
```

建议将仓库放在较短路径，例如 `C:\src\kefu`，并确保终端、Git 与编辑器使用 UTF-8，以避免中文文件名和 Windows 长路径问题。

只有以下测试全部通过后，才能把原生 Windows 标记为正式支持：

```text
dependency installation
runtime artifact extraction
Milvus DB build/open/reopen
embedding smoke
reranker smoke
retrieval smoke
provider probe
full pytest
path traversal/security tests
stage timing contract tests
```

在完成这些验证前，推荐继续使用 WSL2。

## 9. 可复现性边界

以下内容已固定：

```text
Python minor version range
Python dependency versions
dataset/split/corpus manifests
model aliases
worker/concurrency
random seed
warm-up policy
cache policy
retrieval reload policy
KG disabled status
provider mode
```

以下内容无法仅由 Git 完全固定，运行报告必须逐次记录：

```text
Hosted model provider revision
Provider availability and rate limits
Network latency
API retry/timeout events
Local machine load
Secret values
OS-specific filesystem behavior
```

每次正式运行前应保存 commit SHA、config hash、dataset hash、split hash、corpus hash、模型名、worker、concurrency 和 Provider probe 结果。

## 10. 常用检查命令

```bash
git status --short
git rev-parse HEAD
git lfs ls-files
.venv-baseline-v1/bin/python --version
.venv-baseline-v1/bin/python -m pytest -q
.venv-baseline-v1/bin/python evaluation/scripts/check_secrets_v1.py
.venv-baseline-v1/bin/python evaluation/scripts/network_preflight_v1.py --attempts 5 --timeout 8
```

任何正式指标必须明确区分：

```text
Phase1 Diagnostic Baseline
Baseline V1 DEV
Baseline V1 HELDOUT
UNVALIDATED_JUDGE_METRIC
Human-Verified metric
```
