#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
timestamp="${1:?usage: package_baseline_v1_audit.sh YYYYMMDDTHHMMSSZ}"
audit_txt="audit/DOWNLOAD_FOR_CHATGPT/INTERX_BASELINE_V1_AUDIT_${timestamp}.txt"
if [[ ! -f "$audit_txt" ]]; then
  echo "missing audit text: $audit_txt" >&2
  exit 2
fi

stage_dir="$(mktemp -d /tmp/interx-v1-audit.XXXXXX)"
review_root="$stage_dir/InterX_Baseline_V1_Review"
mkdir -p "$review_root"

copy_file() {
  local src="$1"
  mkdir -p "$review_root/$(dirname "$src")"
  cp -a "$src" "$review_root/$src"
}

copy_tree_files() {
  local root="$1"
  while IFS= read -r -d '' src; do
    copy_file "$src"
  done < <(find "$root" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0)
}

files=(
  pyproject.toml requirements-baseline-v1.lock scripts/reproduce_baseline_v1.sh scripts/package_baseline_v1_audit.sh
  agentic-rag/ch-question.csv agentic-rag/en-question.csv
  agentic-rag/answers/ch-answers/per_question/65.json
  agentic-rag/answers/ch-answers/evidence-notes/65.md
  agentic-rag/answers/ch-answers/ch-answers.csv
  agentic-rag/answers/ch-answers/ch-answers.jsonl
  agentic-rag/answers/en-answers/per_question/305.json
  agentic-rag/answers/en-answers/answers.csv
  agentic-rag/answers/en-answers/answers.jsonl
  answer/configs/baseline_v1.yaml
  chat/.env.example chat/configs/default.yaml
  process/configs/default.yaml process/requirements.txt process/src/process_chunk/config.py
  retrieval/configs/default.yaml
  gateway/requirements.txt gateway/litellm/config.template.yaml
  gateway/scripts/build_multi_upstream_config.py gateway/scripts/start_local.sh
  gateway/scripts/stop_gateway.sh gateway/scripts/gateway_status.sh
  web/app.py evaluation/configs/baseline_v1.yaml evaluation/schemas/query_trace_v1.json
  evaluation/gold/gold.jsonl evaluation/gold/gold_build_config.json
  evaluation/results/baseline350/metrics.json
  kg/configs/baseline_v1_train_only.yaml kg/state/semantic_edges.json
  kg/.agents/skills/kg-cold-start/scripts/resolve_refs.py
  kg/.agents/skills/kg-cold-start/scripts/line_to_chunk.py
)
for src in "${files[@]}"; do
  copy_file "$src"
done

trees=(
  answer/src/answer retrieval/src/retrieval chat/src/chat chat/tests
  evaluation/scripts evaluation/tests evaluation/audits evaluation/splits/v1 evaluation/gold_v2
  evaluation/judge evaluation/test_results evaluation/results/baseline_v1 evaluation/baselines
  kg/state/v1_train_only kg/state/v1_source_rebuild
)
for root in "${trees[@]}"; do
  copy_tree_files "$root"
done

tracked_paths=(
  agentic-rag/answers/ch-answers/evidence-notes/65.md
  agentic-rag/answers/ch-answers/per_question/65.json
  agentic-rag/answers/en-answers/per_question/305.json
  agentic-rag/en-question.csv
  answer/src/answer/config.py answer/src/answer/models.py answer/src/answer/normalizer.py
  answer/src/answer/pipeline.py answer/src/answer/query_rewrite.py answer/src/answer/router.py
  retrieval/src/retrieval/dense.py retrieval/src/retrieval/rerank.py
  retrieval/src/retrieval/retriever.py retrieval/src/retrieval/types.py
  chat/.env.example chat/configs/default.yaml chat/src/chat/api.py chat/src/chat/config.py chat/src/chat/store.py
  chat/tests/test_api.py chat/tests/test_chat.py web/app.py
  process/configs/default.yaml process/requirements.txt process/src/process_chunk/config.py
  gateway/requirements.txt gateway/litellm/config.template.yaml
  gateway/scripts/build_multi_upstream_config.py gateway/scripts/start_local.sh
  gateway/scripts/stop_gateway.sh gateway/scripts/gateway_status.sh
)
git diff --binary -- "${tracked_paths[@]}" > "$review_root/GIT_DIFF_V1.patch"
git status --short > "$review_root/GIT_STATUS_AT_REVIEW.txt"
printf '%s\n' \
  'This worktree was already broadly dirty before Baseline V1 work began.' \
  'GIT_DIFF_V1.patch is restricted to tracked files touched for this task; new files are included as full snapshots.' \
  'No .env file, rendered gateway config, secret value, model weight, cache, image duplicate, or graph database is included.' \
  'No baseline-v1 tag was created because formal DEV/HELDOUT runs did not pass their online preconditions.' \
  > "$review_root/PREEXISTING_WORKTREE_NOTICE.txt"

(
  cd "$review_root"
  find . -type f ! -name FILE_MANIFEST_SHA256.txt -print0 | sort -z | xargs -0 sha256sum > FILE_MANIFEST_SHA256.txt
)

zip_path="$repo_root/audit/DOWNLOAD_FOR_CHATGPT/INTERX_BASELINE_V1_REVIEW_${timestamp}.zip"
(
  cd "$stage_dir"
  python3 -m zipfile -c "$zip_path" InterX_Baseline_V1_Review
)
(
  cd "$repo_root/audit/DOWNLOAD_FOR_CHATGPT"
  sha256sum "$(basename "$zip_path")" "$(basename "$audit_txt")" > SHA256SUMS.txt
)
echo "staging retained at: $stage_dir"
echo "wrote: $zip_path"
