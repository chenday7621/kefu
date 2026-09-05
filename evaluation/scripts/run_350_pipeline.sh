#!/usr/bin/env bash
# Full 350-question Original Baseline pipeline.
#   1. gateway pre-flight (abort if unhealthy)
#   2. run all questions (resume-safe: already-recorded ids are skipped)
#   3. compute metrics -> 4. generate report + pending-audit lists
# Extra args are passed to run_baseline.py (e.g. --retry-errors).
set -u
cd "$(dirname "$0")/../.."
OUT=evaluation/results/baseline350
mkdir -p "$OUT"

echo "=== [$(date '+%F %T')] pre-flight gateway probe ==="
chat/.venv/bin/python evaluation/scripts/gateway_probe.py || {
  echo "=== ABORTED: gateway unhealthy ==="; exit 2; }

echo "=== [$(date '+%F %T')] run baseline (resume-safe) ==="
chat/.venv/bin/python evaluation/scripts/run_baseline.py --out "$OUT/raw.jsonl" "$@"

echo "=== [$(date '+%F %T')] compute metrics ==="
python3 evaluation/scripts/compute_metrics.py \
  --raw "$OUT/raw.jsonl" --gold evaluation/gold/gold.jsonl \
  --out "$OUT/metrics.json" --errors-out "$OUT/error_samples.jsonl" \
  > "$OUT/metrics_stdout.json"

echo "=== [$(date '+%F %T')] generate report + audit lists ==="
python3 evaluation/scripts/make_350_report.py --dir "$OUT"

echo "=== [$(date '+%F %T')] PIPELINE DONE ==="
