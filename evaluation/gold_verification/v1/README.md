# InterX Dev / Heldout Human Gold Verification V1

This directory contains **machine-proposed review material**, not Human-Verified Gold.

- Source layer: proposed original-manual spans and exact source text.
- Semantic layer: the Silver reference answer plus conservative, source-verbatim proposed facts.
- Retrieval-mapping layer: chunk IDs derived only from manual identity and source-line overlap.

Every `human_review` starts as `UNREVIEWED`, with `overall_decision = null`. No script in the preparation flow assigns `APPROVE`. Only `APPROVE` or `EDITED_APPROVE` records that pass `validate_human_gold_review.py` may be emitted by `build_verified_gold_v1.py`.

Dev and Heldout are kept in separate directories. The sheets deliberately omit current model answers, retrieval ranks/scores, baseline correctness, and hit indicators. Heldout must not be used for error-driven development after it is reviewed and sealed.

## Workflow

1. Rebuild proposed assets with `python3 evaluation/scripts/prepare_human_gold_verification_v1.py --force`.
2. Review `dev/DEV_GOLD_REVIEW.csv` and `heldout/HELDOUT_GOLD_REVIEW.csv`, using each split's `items/` pages for context.
3. Validate edited sheets with `python3 evaluation/scripts/validate_human_gold_review.py <CSV>`.
4. Preview eligible reviewed records with `build_verified_gold_v1.py --preview`. Finalization refuses incomplete review sets.
5. After complete Heldout review and final build only, explicitly run `seal_heldout_gold.py --acknowledge-seal`.

Candidate fields remain proposals even when automatic source resolution succeeds. A resolved path or line span means only that the cited bytes were located; it does not mean a human has accepted their semantics.
