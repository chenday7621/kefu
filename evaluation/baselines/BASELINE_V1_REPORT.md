# InterX Formal Baseline V1 — Readiness Report

`BASELINE_V1_READY = NO`

This report separates completed evaluation-foundation work from the formal
model-backed run. The foundation is reproducible and tested, but no Baseline V1
quality or latency metric exists yet: both the answer-model preflight and the
retrieval smoke failed on external upstream timeouts. Phase1 data was not
relabeled or substituted.

## Identity and frozen inputs

- Current repository HEAD: `9679bd23c01dbd61f6cf51f5d3d831f12d3c4f08`
- Existing tag at HEAD: `phase1-baseline`
- Intended V1 tag: **not created**; tagging an unexecuted baseline would be false
- Dataset: **InterX-350 Silver Benchmark**
- Dataset hash: `018a03ddbba5a649cddeb8fed677352f958c60853121a2e316d820b079bd8ae2`
- Split hash: `34019e0e071a08818169979d1948be909d965872fa763555874048008de3be5c`
- Corpus hash: `c61267821fead7178cdd94fb0e686fd5146e0cacf722f6fd0c0cbde6569a5303`
- Reference V2 hash: `262786ea0604d6e4e01e71e74aeb1de08f81e209aadbea62309e4f3e5d9774b8`
- Reference V2 schema hash: `4f4977d46d10ae8c51ff41ca0e292b312d47ceb5eee87c57b0249d92a90af1ad`
- KG build-manifest hash: `4b22a52e3527124cb3c5e14e8acece847d354e386cc9118d266079182186cab7`
- Formal protocol hash: `a491de72cd980fdb81ba5c358dc9bf94f141a99d39e31eb23c23611f4265e320`
- Dependency lock hash: `c3ac78b0f98f4bd58348e6ddb125f009cce9a90475f62a3d8ff3662aa1c12f65`

The working tree contained extensive changes before this task and is not clean.
The V1 review package therefore includes source snapshots and a Git patch, but a
new commit/tag was deliberately not manufactured from unrelated user changes.

## Phase1 Diagnostic Baseline (preserved, not V1)

The original `evaluation/results/baseline350/` remains intact. Its raw-file hash
is pinned in the Phase1 manifest and verified by test.

| Diagnostic metric | Value | Eligible n |
|---|---:|---:|
| Chunk Hit@1 | 0.6213 | 235 |
| Chunk Hit@3 | 0.7702 | 235 |
| Chunk Hit@5 | 0.8383 | 235 |
| MRR | 0.7139 | 235 |
| Chinese Hit@1 | 0.3077 | 78 |
| English Hit@1 | 0.7771 | 157 |
| Document Hit@1 / Hit@5 | 0.8994 / 0.9817 | 328 |
| P50 / P95 | 43.0s / 113.8s | 350 |
| Router empty output | 242 / 350 | — |

These remain diagnostic only: the references are Silver, pre-V1 ID 65 was
misbound, the KG used all 350 QA evidence references, the Judge was incompatible,
and concurrency/reload conditions were mixed.

## Data governance and frozen split

- 350/350 questions and answers joined; duplicate and missing ID counts are zero.
- Coverage remains chunk 235, document 328, image 296.
- Quality states: 349 `silver`, 1 `verified`, 0 `quarantined`.
- ID 65 was repaired at the source per-question answer file from the blower
  manual lines 54–68 and 75–111. Only this source binding is marked verified.
- ID 305 received formatting/escaping normalization only; semantics were not
  changed and it remains Silver.
- Question type is null with `unavailable_not_inferred`; labels were not guessed.

The split uses seed `20260904`. It first creates connected components of manuals:
a multi-manual question joins all constituent manuals, preventing an `A|B` record
from crossing a split with an `A` or `B` record. It then deterministically
stratifies language and chunk/document/image coverage.

| Split | Total | zh | en | Chunk | Document | Image |
|---|---:|---:|---:|---:|---:|---:|
| Train | 243 | 116 | 127 | 164 | 229 | 198 |
| Dev | 54 | 22 | 32 | 36 | 50 | 51 |
| Heldout | 53 | 25 | 28 | 35 | 49 | 47 |
| Quarantined | 0 | — | — | — | — | — |

Atomic manual overlap and ID overlap are both zero. Heldout is manual-disjoint
and is guarded by an explicit `--ack-heldout` flag in the runner.

## Reference Schema V2

All 350 derived records are rebuilt by script. Every resolved chunk ID is joined
back to corpus text. Records without chunk Gold use source evidence only where it
can be reliably resolved; unavailable fields remain null. Evidence text is
available for 250/350 records. Schema/semantic validation passes with zero errors.

The answer payload now has optional `citation_chunk_ids` and `source_metadata`
fields for future use. V1 does not claim or score citation attribution.

## Judge and human calibration

`run_judge.py` consumes Reference V2 rather than obsolete input fields and
preserves per-item inputs, evidence, raw response, parsed scores/status, model,
prompt version/hash, usage, latency, and errors. The dry-run compatibility check
passes. Scores are hard-labelled `UNVALIDATED_JUDGE_METRIC`.

A deterministic, version-blinded 50-item Train/Dev sample exists: 25 calibration
and 25 validation items, stratified over language, retrieval outcome, manual, and
available coverage. CSV/JSONL round-trip and scoring support Pearson, Spearman,
MAE, binary agreement/accuracy, and F1. Human scoring has not been performed.

No model-backed Judge output was generated because the answer-model preflight
failed. Consequently there is no Answer Correctness, Completeness, or
Faithfulness result to report.

## KG leakage decision

Fresh evidence resolution was rebuilt after source governance. The prepared
Train-filtered inputs contain 1,315 evidence records and 762 QA-derived semantic
edges from 243 Train question IDs; Dev and Heldout answer-ID overlap are both
empty. Both `CO_EVIDENCE` inputs and retained `SEMANTIC` edges are filtered.

The legacy runtime graph is not certified to honor the new graph path and retains
historical all-350 derivation. Therefore the formal V1 answer config sets
`KG enabled = false`. This is the leakage-safe fallback required by the protocol;
no Dev/Heldout answer can receive context from the legacy QA-derived KG.

## Formal execution protocol and observability

- Python 3.12; exact transitive lock file.
- One query worker, concurrency one, Train warm-up ID 241 discarded.
- Retrieval corpus loaded once at startup; per-query reload records zero with
  explicit `startup_once` status. Startup reload time is stored separately.
- Answer alias `qwen3.6-plus`; rewrite alias `qwen3-max`; embedding
  `qwen3-vl-embedding`; reranker `qwen3-rerank`.
- Generation temperature 0.1; all token limits, timeouts, retries, retrieval
  settings, cache policy, corpus hash, seed, and outlier policy are frozen in
  `evaluation/configs/baseline_v1.yaml`.
- P50/P95 are primary latency statistics. Samples over 300 seconds are retained
  in the all-sample population and listed separately.

The query trace contract covers router, rewrite, decompose, reload, embedding,
dense, BM25, fusion, rerank, KG, three generation branches, ensemble, VLM, and
total time. It also records model aliases, calls, reported token usage/coverage,
retry/timeout counts, fallback/degraded state, cache status, trace UUID, worker,
and concurrency. Offline contract tests pass; live end-to-end trace verification
is blocked by the upstream timeouts.

`recall_meta.elapsed_seconds` is retained for compatibility and is never called
pure retrieval time in V1 reporting.

## Minimum demonstration security

- Bearer Token is compared with the configured value using constant-time compare
  and fails closed when the server token is absent.
- `user_id`, `session_id`, and image IDs have allow-listed characters; resolved
  session paths must stay under the session root.
- Request, question text, decoded image, image count, and base64 format are bounded.
- Partial temporary image files are cleaned on parse failure.
- Local `.env` files are mode 0600; the permission audit reads no secret values.
- Request-body verbose logging is disabled by default.
- The web client has no built-in fallback token.

## Reproduction and tests

The root `pyproject.toml` installs all sibling packages, and
`requirements-baseline-v1.lock` pins all resolved dependencies. The default
process path recursively discovers 20 Chinese and 20 English manuals. A new
Python 3.12.8 environment was created from the lock, the repository was installed
editable, all derived dataset/split/Reference/KG inputs were rebuilt, and the
offline reproduction script completed.

Final test result: **87 passed, 2 dependency deprecation warnings**. Coverage
includes dataset audit, Reference V2 validation, evidence resolution, split
reproducibility, ID/manual non-overlap, Heldout guard, KG Train-only source,
Judge compatibility/calibration metrics, path safety, token validation, stage
trace fields, Phase1 preservation, and bilingual process-path discovery.

## DEV / HELDOUT results

| Formal split | Run status | Retrieval/document/image | Answer Judge | Latency/token/calls |
|---|---|---|---|---|
| DEV | `NOT_RUN_PRECONDITION_FAILED` | unavailable | unavailable | unavailable |
| HELDOUT | `NOT_RUN_PRECONDITION_FAILED` | unavailable | unavailable | unavailable |

The local LiteLLM process started and passed `/health/liveliness`, but the frozen
`qwen3.6-plus` completion timed out in two 90-second no-retry preflights. The
retrieval smoke also exceeded a 180-second hard timeout. A five-attempt no-key,
no-payload transport diagnostic observed four TCP timeouts and one successful
TLS handshake to `dashscope.aliyuncs.com:443`, demonstrating intermittent rather
than usable reachability. The LiteLLM cancellation trace likewise stopped in the
upstream socket-connect path. No proxy or second configured upstream is
available. Formal runs were not started, no placeholder raw result was written,
and no Phase1 metric was substituted.

## Acceptance audit

| Gate | Status | Evidence |
|---|---|---|
| A. Data | PASS | 350-record audit; ID 65 repaired; ID 305 normalized; frozen split |
| B. Reference V2 | PASS | evidence-bearing generated records; validation 0 errors |
| C. Judge | PARTIAL/BLOCKED | V2 compatibility and dry-run pass; model run unavailable; metric unvalidated |
| D. KG | PASS | formal KG disabled; prepared Train-only inputs have zero Dev/Heldout overlap |
| E. Timing | PARTIAL/BLOCKED | implementation and contract tests pass; live trace not produced |
| F. Reproducibility | PARTIAL/BLOCKED | clean offline rebuild/tests pass; online smoke fails upstream timeout |
| G. Security | PASS | auth/path/input/secret-mode tests pass |
| H. Results | FAIL | neither formal DEV nor HELDOUT completed |

## Blockers and known limitations

1. The configured DashScope endpoint is not stably usable from this execution
   environment: four of five transport attempts timed out before TCP connection,
   while one reached TLS; two frozen-model completions timed out at 90 seconds.
   There is no proxy or alternate configured upstream; formal DEV/HELDOUT and
   Judge runs cannot proceed without an external-state change.
2. No formal raw results means trace behavior is unit/contract verified but not
   yet demonstrated on a live query.
3. Human Judge calibration is prepared but not scored; any future Judge metric
   remains unvalidated until the validation subset is completed.
4. The 350 reference answers remain primarily Agent-generated Silver data; only
   ID 65's repaired source binding is explicitly verified.
5. Evidence text is unavailable for 100 records; their faithfulness Judge score
   must not be treated like evidence-backed examples.
6. Manual-disjoint Heldout is intentionally strict and may have product/manual
   distribution shift; comparisons must use this exact split hash.
7. Provider-side model revisions and cache metadata were not available from the
   failed run; aliases alone do not fully pin hosted model weights.
8. The legacy all-350 KG remains as historical data but is forbidden by the V1
   config. No train-only runtime graph was certified.
9. The pre-existing dirty worktree prevents an honest V1 commit/tag until changes
   are reviewed and isolated. `baseline-v1` has not been created.

Because Gates C/E/F/H are not fully satisfied, the only honest conclusion is:

`BASELINE_V1_READY = NO`
