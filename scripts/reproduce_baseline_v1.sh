#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${INTERX_V1_PYTHON:-python3.12}"
venv_dir="${INTERX_V1_VENV:-$repo_root/.venv-baseline-v1}"

if [[ ! -x "$venv_dir/bin/python" ]]; then
  uv venv --python "$python_bin" "$venv_dir"
fi
uv pip install --python "$venv_dir/bin/python" -r requirements-baseline-v1.lock
uv pip install --python "$venv_dir/bin/python" --no-deps -e .

v1_python="$venv_dir/bin/python"

baseline_preflight() {
  "$v1_python" evaluation/scripts/network_preflight_v1.py --attempts 5 --timeout 8
  "$v1_python" evaluation/scripts/gateway_probe.py \
    --timeout 90 \
    --out evaluation/results/baseline_v1/preflight/gateway_probe.json
}

"$v1_python" evaluation/scripts/sync_silver_v1.py
"$v1_python" evaluation/scripts/build_gold.py
"$v1_python" evaluation/scripts/audit_dataset_v1.py
"$v1_python" evaluation/scripts/make_splits_v1.py
"$v1_python" evaluation/scripts/build_gold_v2.py
"$v1_python" evaluation/scripts/validate_gold_v2.py
mkdir -p kg/state/v1_source_rebuild
"$v1_python" kg/.agents/skills/kg-cold-start/scripts/resolve_refs.py \
  --answers-dir agentic-rag/answers \
  --process-dir process/artifacts/manuals \
  --output kg/state/v1_source_rebuild/evidence_resolved.json
"$v1_python" kg/.agents/skills/kg-cold-start/scripts/line_to_chunk.py \
  --evidence kg/state/v1_source_rebuild/evidence_resolved.json \
  --process-dir process/artifacts/manuals \
  --output kg/state/v1_source_rebuild/evidence_mapped.json
"$v1_python" evaluation/scripts/prepare_train_only_kg_v1.py \
  --mapped kg/state/v1_source_rebuild/evidence_mapped.json \
  --semantic kg/state/semantic_edges.json \
  --out-dir kg/state/v1_train_only
"$v1_python" evaluation/scripts/sample_human_judge_v1.py --size 50
"$v1_python" evaluation/scripts/build_baseline_v1_manifest.py
"$v1_python" evaluation/scripts/check_secrets_v1.py
"$v1_python" -m pytest evaluation/tests answer/tests retrieval/tests chat/tests -q

if [[ "${INTERX_V1_SMOKE:-0}" == "1" ]]; then
  : "${INTERX_GATEWAY_API_KEY:?INTERX_GATEWAY_API_KEY is required for smoke evaluation}"
  : "${INTERX_GATEWAY_BASE_URL:?INTERX_GATEWAY_BASE_URL is required for smoke evaluation}"
  baseline_preflight
  "$v1_python" evaluation/scripts/run_baseline.py \
    --config answer/configs/baseline_v1.yaml \
    --split-file evaluation/splits/v1/dev.jsonl \
    --ids 1,164 \
    --warmup-ids 241 \
    --workers 1 \
    --out evaluation/results/baseline_v1/smoke/raw.jsonl
fi

if [[ "${INTERX_V1_FULL:-0}" == "1" ]]; then
  : "${INTERX_GATEWAY_API_KEY:?INTERX_GATEWAY_API_KEY is required for formal evaluation}"
  : "${INTERX_GATEWAY_BASE_URL:?INTERX_GATEWAY_BASE_URL is required for formal evaluation}"
  baseline_preflight
  "$v1_python" evaluation/scripts/run_baseline.py \
    --config answer/configs/baseline_v1.yaml \
    --split-file evaluation/splits/v1/dev.jsonl \
    --warmup-ids 241 --workers 1 \
    --out evaluation/results/baseline_v1/dev/raw.jsonl
  "$v1_python" evaluation/scripts/compute_metrics_v1.py \
    --raw evaluation/results/baseline_v1/dev/raw.jsonl \
    --split-file evaluation/splits/v1/dev.jsonl \
    --out evaluation/results/baseline_v1/dev/metrics.json
  "$v1_python" evaluation/scripts/run_baseline.py \
    --config answer/configs/baseline_v1.yaml \
    --split-file evaluation/splits/v1/heldout.jsonl \
    --ack-heldout --warmup-ids 241 --workers 1 \
    --out evaluation/results/baseline_v1/heldout/raw.jsonl
  "$v1_python" evaluation/scripts/compute_metrics_v1.py \
    --raw evaluation/results/baseline_v1/heldout/raw.jsonl \
    --split-file evaluation/splits/v1/heldout.jsonl \
    --out evaluation/results/baseline_v1/heldout/metrics.json
fi

echo "Baseline V1 deterministic preparation complete."
