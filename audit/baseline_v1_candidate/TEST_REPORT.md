# Baseline V1 Candidate Test Report

`TEST_STATUS = PASS`

## Offline reproduction

- Command: `bash scripts/reproduce_baseline_v1.sh`
- Exit status: 0
- Result: 91 passed, 2 dependency deprecation warnings
- Runtime corpus: 7,293 chunks materialized in a local ignored Milvus database
- Dataset audit: 350 records; chunk/doc/image coverage 235/328/296
- Split: Train 243, Dev 54, Heldout 53, Quarantined 0
- Split hash: `34019e0e071a08818169979d1948be909d965872fa763555874048008de3be5c`
- Reference V2 validation: pass, 350 records, zero errors
- KG train-only audit: pass, zero Dev/Heldout answer-ID overlap

This command makes no model calls and does not execute formal DEV or HELDOUT.
The complete captured output is in `test_logs/reproduce_baseline_v1_final.txt`.

## Complete configured pytest suite

- Command: `.venv-baseline-v1/bin/python -m pytest -q`
- Exit status: 0
- Result: 114 passed, 21 skipped, 2 dependency deprecation warnings
- The 21 skips are integration cases requiring the historical runtime graph at
  `kg/state/graph.db`. Formal Baseline V1 intentionally disables that leaking
  graph. Train-only source/leakage tests executed and passed.
- The historical `kg/tests/test_kg_compare.py` live experiment is now guarded by
  `main()` and has no import-time network or absolute-path write side effect.

The captured output is in `test_logs/pytest_final.txt`.

## Judge compatibility

- `run_judge.py --dry-run --limit 3`: exit 0
- Three inputs were resolved from Reference V2 and prompts were constructed.
- No Judge model call was made.
- Metric status remains `UNVALIDATED_JUDGE_METRIC`.

## Connectivity smoke

| Probe | Status | Evidence |
|---|---|---|
| Direct DashScope | PARTIAL / overall fail | Answer pass (1.908s), Judge pass (1.299s), Rewrite timeout at 25.209s |
| Retrieval | PASS | small/mid/big 5/5/3; embedding/dense/BM25/fusion/rerank all `ok`; 71.233s wall time |
| Temporary local LiteLLM | PASS | liveliness pass and real `qwen3.6-plus` completion pass |

All reports are credential-free. The temporary LiteLLM process was stopped and
its generated secret-bearing configuration was removed after the probe.

## Explicit non-execution

- Formal DEV: not run
- Formal HELDOUT: not run
- Model-backed Answer Judge: not run
- `baseline-v1` tag: not created
