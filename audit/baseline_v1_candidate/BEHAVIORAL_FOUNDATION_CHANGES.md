# Behavioral Foundation Changes

This Candidate starts from `phase1-baseline` at
`9679bd23c01dbd61f6cf51f5d3d831f12d3c4f08`. The changes below are required
for data correctness, leakage control, observability, security, or clean
reproduction. They are not presented as algorithm improvements.

| Area | Previous behavior | Candidate behavior | Foundation rationale | May change Phase1 numbers |
|---|---|---|---|---|
| Silver ID 65 | The blower question was bound to a drill answer. | The source per-question answer is repaired from blower-manual lines 54–68 and 75–111; aggregates are rebuilt. | Correct a confirmed source-binding defect without guessing. | Yes, for ID 65 answer/reference evaluation. |
| Silver ID 305 | Equivalent quote/escape forms differed across source files. | Strings are normalized without semantic edits. | Stable joins and hashes. | No expected semantic effect. |
| KG runtime | The historical graph was derived from all 350 QA evidence references. | Formal V1 config disables KG. Separately generated QA-derived graph inputs are Train-only and audited for zero Dev/Heldout IDs. | Prevent evaluation leakage. | Yes, answer context can differ from Phase1. |
| Retrieval reload lifecycle | `answer()` reloaded corpus/BM25 for every question. | Formal V1 uses an explicit `startup_once` policy; legacy `per_query` remains available. | Fix a lifecycle bug and make timing/cache state unambiguous. | Latency changes; retrieval results should not intentionally change, but provider/index nondeterminism remains possible. |
| Provider route | Phase1 default used a local gateway alias. | Formal V1 explicitly pins direct DashScope and the real model name. LiteLLM is an explicit optional profile and never a silent fallback. | Record the actual provider/model and remove hidden routing state. | Transport latency/failure behavior can differ; model semantics are not optimized. |
| Router model resolution | The environment-only fallback called `resolve_model_name` with an obsolete signature. | The configured env file, explicit name, and env-name arguments are passed correctly. | Repair configuration compatibility. Router prompt, token limit, and fallback policy are unchanged. | Only configurations without an explicit model name can differ. |
| Query rewrite | Rewrites were generated but not used for retrieval. | The same remains true; calls are timed and failures recorded. | Instrument existing behavior without enabling multi-query retrieval. | No intended retrieval effect. |
| Retrieval instrumentation | Only aggregate elapsed time was exposed. | Embedding, dense, BM25, fusion, rerank, retries, timeouts, cache, calls, and fallbacks are recorded. | Make latency and degraded behavior observable. | No intended scoring effect. |
| Answer instrumentation | LLM stages lacked a uniform trace contract. | Router/rewrite/small/mid/big/ensemble calls record timing, usage, retry, timeout, fallback, model, worker, and concurrency data. | Per-query observability. | No intended prompt or generation-policy effect. |
| Answer result schema | Final answers exposed content/images only. | Optional citation chunk IDs, source metadata, and trace fields are preserved. | Enable future attribution evaluation without claiming it now. | No intended answer-content effect. |
| Corpus discovery | The default process path did not find the repository-level bilingual manuals recursively. | The default points at repository `data/` and discovers Markdown recursively. | Make a clean checkout build the intended existing corpus. Chunk formation code and thresholds are unchanged. | Corpus availability changes from incomplete/broken defaults to the intended 40-manual input. |
| Historical manual paths | Silver evidence provenance points at legacy `agentic-rag/*-manual` paths. | Builders resolve those paths to committed `data/*-manual` files. | Recover evidence text from the same manuals after repository layout migration. | Evaluation coverage changes from a broken build to the documented 235/328/296 boundary. |
| HTTP security | Any non-empty bearer token passed; identifiers and request sizes were weakly bounded. | Constant-time configured-token comparison, fail-closed auth, ID/path containment, request/text/image limits, and quiet request logging are enforced. | Minimum safe public-demo boundary. | Invalid/oversized requests now fail; valid QA algorithm behavior is unchanged. |
| Dependency/runtime setup | Dependencies were open-ended and sibling packages relied on ambient paths. | Python 3.12 dependency lock, installable root package, runtime artifact preparation, and one reproduction entry are provided. | Reproducible clean environment. | Dependency versions are frozen and may expose version-specific behavior. |

## Explicit non-changes

- No changed file implements chunk formation or title-aware merging.
- `retrieval/fusion.py`, sparse scoring, and retrieval weights/top-k values are unchanged.
- Dense and rerank requests retain their original models, payloads, retry policy,
  and ranking calls; wrappers only record telemetry.
- Query rewrite output is still metadata-only and is not passed to retrieval.
- No answer, router, rewrite, or rerank prompt file is changed.
- No VLM, question-decomposition, multi-query RRF, manual router, adaptive
  generation, Agent, MCP, SFT, or RL code is included.
- Formal DEV and HELDOUT were not run, and no `baseline-v1` tag was created.
