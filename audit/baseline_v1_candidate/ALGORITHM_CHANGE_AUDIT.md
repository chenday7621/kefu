# Algorithm Change Audit

`ALGORITHM_OPTIMIZATION_OCCURRED = NO`

The audit compares the complete Candidate tree with
`9679bd23c01dbd61f6cf51f5d3d831f12d3c4f08`.

## Retrieval and chunking

- No diff exists in `retrieval/fusion.py`, `retrieval/sparse.py`, or the
  retrieval configuration containing dense/BM25/RRF weights and top-k values.
- Changes in `dense.py`, `rerank.py`, `retriever.py`, and `types.py` add stage
  timers, counters, model names, cache state, retry/timeout state, and fallback
  reporting around the existing calls.
- The order and arguments of BM25, embedding, Milvus search, RRF fusion, and
  reranking are unchanged.
- `process_chunk/config.py` changes only source-file discovery from a broken
  non-recursive path to recursive discovery of the existing bilingual corpus.
  No parser, splitter, chunk size, overlap, hierarchy, or title handling code
  changed.

## Query, router, generation, and KG

- Query rewrite is invoked exactly once as before, and retrieval is called with
  the original question. Rewrite variants remain metadata-only.
- Router prompt, `max_tokens=32`, temperature, route parsing, and fallback-to-RAG
  policy are unchanged. One obsolete model-name configuration call is repaired.
- The small/mid/big parallel generation plus ensemble topology and all prompt
  semantics are unchanged. Trace wrappers do not select a different context or
  generation branch.
- Formal Baseline V1 disables KG to remove known all-350 QA leakage. Train-only
  inputs are retained as audit assets but are not enabled at runtime.

## Prohibited-feature scan

The Candidate includes none of the original dirty-workspace Phase2 VLM,
question-decomposition, multimodal-RAG, query-RRF experiment, manual-routing,
adaptive-generation, Agent/MCP, or model-training files. The explicit
`decompose_ms` trace slot is present with status `disabled`; it is a schema field,
not a decomposition implementation.

Foundation behavior changes that can affect comparability are disclosed in
`BEHAVIORAL_FOUNDATION_CHANGES.md`; no such change is claimed as an accuracy
improvement.
