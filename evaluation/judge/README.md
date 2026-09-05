# Baseline V1 Judge

`run_judge.py` consumes Gold/Reference Schema V2 and preserves every Judge input,
raw response, parsed score, model, prompt hash, token usage, latency, and parse
status. Image quality remains a deterministic metric; text citation attribution is
not scored until production answers expose citation chunk IDs.

All scores are labelled `UNVALIDATED_JUDGE_METRIC` until a human calibration and
held-back validation workflow establishes acceptable agreement.

- `prompts/`: versioned Judge prompts.
- `results/`: append-only per-query Judge outputs.
- `calibration/`: blinded human-review samples and agreement reports.
