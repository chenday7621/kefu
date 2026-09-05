# Baseline V1 timing and trace contract

Every successful query emits a UUID `trace_id`, worker/concurrency identity,
per-stage duration and status, call counters, token coverage, model aliases,
fallback/degraded state, cache state, retry count, timeout count, and total time.

Stages are `router`, `rewrite`, `decompose`, `reload`, `embedding`, `dense`,
`bm25`, `fusion`, `rerank`, `kg`, `small_generation`, `mid_generation`,
`big_generation`, `ensemble`, and `vlm`. A stage that does not execute records
zero milliseconds with an explicit `disabled`, `not_run`, `startup_once`, or
other status. Startup-only reload duration is recorded at run-record level as
`startup_reload_ms`; per-query `reload` is zero with `startup_once` status.

`recall_meta.elapsed_seconds` is retained for backward compatibility but is not
called retrieval latency in V1 reporting. It includes pre-retrieval orchestration
and KG when enabled. Formal reports use the detailed trace fields and P50/P95;
samples over 300 seconds remain in the all-sample population and are also listed
separately.

Token totals may be null when an upstream response does not report usage. The
trace includes an explicit coverage ratio rather than estimating missing usage.
Gateway cache status is `unreported` unless the gateway returns auditable cache
metadata.
