#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

python3 evaluation/scripts/prepare_human_gold_verification_v1.py --force
python3 evaluation/scripts/validate_human_gold_review.py evaluation/gold_verification/v1/dev/DEV_GOLD_REVIEW.csv
python3 evaluation/scripts/validate_human_gold_review.py evaluation/gold_verification/v1/heldout/HELDOUT_GOLD_REVIEW.csv
python3 evaluation/scripts/build_verified_gold_v1.py --preview

echo "Prepared UNREVIEWED proposal assets only. No formal DEV/Heldout run and no Heldout seal were performed."
