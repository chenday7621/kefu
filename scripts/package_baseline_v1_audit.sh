#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

timestamp="${1:?usage: package_baseline_v1_audit.sh YYYYMMDDTHHMMSSZ [output_dir]}"
output_dir="${2:-$repo_root/audit/DOWNLOAD_FOR_CHATGPT}"
audit_txt="$output_dir/INTERX_BASELINE_V1_CANDIDATE_AUDIT_${timestamp}.txt"
zip_path="$output_dir/INTERX_BASELINE_V1_CANDIDATE_REVIEW_${timestamp}.zip"
source_commit="9679bd23c01dbd61f6cf51f5d3d831f12d3c4f08"

if [[ ! -f "$audit_txt" ]]; then
  echo "missing candidate audit text: $audit_txt" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "refusing to package a dirty Candidate worktree" >&2
  exit 2
fi
if [[ "$(git merge-base "$source_commit" HEAD)" != "$source_commit" ]]; then
  echo "Candidate is not descended from phase1-baseline" >&2
  exit 2
fi
if git tag --list baseline-v1 | grep -q .; then
  echo "formal baseline-v1 tag must not exist during Candidate packaging" >&2
  exit 2
fi

mkdir -p "$output_dir"
stage_dir="$(mktemp -d /tmp/interx-v1-candidate-audit.XXXXXX)"
review_root="$stage_dir/InterX_Baseline_V1_Candidate_Review"
mkdir -p "$review_root"

copy_file() {
  local src="$1"
  mkdir -p "$review_root/$(dirname "$src")"
  cp -a "$src" "$review_root/$src"
}

files=(
  audit/baseline_v1_candidate/ALGORITHM_CHANGE_AUDIT.md
  audit/baseline_v1_candidate/BEHAVIORAL_FOUNDATION_CHANGES.md
  audit/baseline_v1_candidate/CONFIG_AND_HASH_MANIFEST.json
  audit/baseline_v1_candidate/CONFIG_AND_HASH_MANIFEST.md
  audit/baseline_v1_candidate/CURRENT_WORKSPACE_CLASSIFICATION.json
  audit/baseline_v1_candidate/CURRENT_WORKSPACE_CLASSIFICATION.md
  audit/baseline_v1_candidate/ORIGINAL_WORKSPACE_SAFETY_CHECK.json
  audit/baseline_v1_candidate/ORIGINAL_WORKSPACE_SAFETY_CHECK.md
  audit/baseline_v1_candidate/TEST_REPORT.json
  audit/baseline_v1_candidate/TEST_REPORT.md
  audit/baseline_v1_candidate/connectivity/litellm_probe_candidate.json
  audit/baseline_v1_candidate/connectivity/provider_probe_candidate.json
  audit/baseline_v1_candidate/connectivity/retrieval_probe_candidate.json
  audit/baseline_v1_candidate/test_logs/judge_compatibility_dry_run.txt
  audit/baseline_v1_candidate/test_logs/pytest_final.txt
  audit/baseline_v1_candidate/test_logs/reproduce_baseline_v1_final.txt
  evaluation/audits/dataset_governance_v1.json
  evaluation/audits/dataset_governance_v1.md
  evaluation/audits/kg_leakage_audit_v1.json
  evaluation/audits/kg_leakage_audit_v1.md
  evaluation/baselines/BASELINE_V1_REPORT.md
  evaluation/baselines/BASELINE_V1_REPRODUCTION.md
  evaluation/baselines/PHASE1_DIAGNOSTIC_BASELINE.md
  evaluation/baselines/TIMING_AND_TRACE_V1.md
  evaluation/baselines/baseline_v1_environment_manifest.json
  evaluation/configs/baseline_v1.yaml
  answer/configs/baseline_v1.yaml
  answer/configs/baseline_v1_litellm_optional.yaml
  evaluation/gold_v2/manifest.json
  evaluation/gold_v2/schema.json
  evaluation/gold_v2/sample.jsonl
  evaluation/gold_v2/validation.json
  evaluation/judge/JUDGE_STATUS_V1.md
  evaluation/judge/README.md
  evaluation/judge/prompts/answer_judge_v1.txt
  evaluation/schemas/query_trace_v1.json
  evaluation/splits/v1/README.md
  evaluation/splits/v1/split_manifest.json
  kg/state/v1_train_only/build_manifest.json
  pyproject.toml
  requirements-baseline-v1.lock
  scripts/reproduce_baseline_v1.sh
)

for src in "${files[@]}"; do
  copy_file "$src"
done
cp -a "$audit_txt" "$review_root/$(basename "$audit_txt")"

git diff --binary "$source_commit..HEAD" > "$review_root/CANDIDATE_COMMIT_DIFF.patch"
git show --stat --oneline --decorate HEAD > "$review_root/CANDIDATE_COMMIT_STAT.txt"
git status --short > "$review_root/CANDIDATE_GIT_STATUS.txt"
git log --oneline --decorate "$source_commit..HEAD" > "$review_root/CANDIDATE_COMMIT_LOG.txt"
printf '%s\n' "$source_commit" > "$review_root/SOURCE_COMMIT.txt"
git rev-parse HEAD > "$review_root/CANDIDATE_COMMIT_SHA.txt"
git branch --show-current > "$review_root/CANDIDATE_BRANCH.txt"

(
  cd "$review_root"
  find . -type f ! -name FILE_MANIFEST_SHA256.txt -print0 \
    | sort -z | xargs -0 sha256sum > FILE_MANIFEST_SHA256.txt
)

(
  cd "$stage_dir"
  python3 -m zipfile -c "$zip_path" InterX_Baseline_V1_Candidate_Review
)
(
  cd "$output_dir"
  sha256sum "$(basename "$zip_path")" "$(basename "$audit_txt")" > SHA256SUMS.txt
)

python3 -c "import shutil; shutil.rmtree('$stage_dir')"
echo "wrote: $zip_path"
echo "wrote: $output_dir/SHA256SUMS.txt"
