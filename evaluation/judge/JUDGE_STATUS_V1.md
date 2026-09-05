# Answer Judge V1 status

Status: **PIPELINE_READY / UNVALIDATED_JUDGE_METRIC**.

The Judge consumes Reference Schema V2 and receives actual evidence text when it
is resolvable. It stores every question, Silver reference answer, evidence block,
system answer, raw Judge response, parsed scores, parse status, model, prompt
version/hash, token usage, latency, and error. It does not read the obsolete
`gold_evidence` or `gold_image_ids` input fields.

The Judge dimensions are answer correctness, completeness, and faithfulness.
Citation/attribution is intentionally not scored in V1 because the frozen answer
pipeline does not yet guarantee `citation_chunk_ids`. Image retrieval remains a
deterministic metric.

The 50-item blinded human workflow is prepared under `calibration/sample_v1`
(25 calibration, 25 validation; Train/Dev only). No human scores have been
entered, so no correlation/agreement claim is valid and no aggregate Judge score
may be described as authoritative accuracy.

The model-backed Judge was not executed because the formal gateway completion
preflight timed out. `run_judge.py --dry-run` passed and is recorded in the test
artifacts.
