# Phase1 Diagnostic Baseline (preserved)

This document freezes the provenance of the pre-V1 run. It does not modify or
replace `evaluation/results/baseline350/`.

- Commit: `9679bd23c01dbd61f6cf51f5d3d831f12d3c4f08`
- Tag at commit: `phase1-baseline`
- Run date: 2026-07-17
- Dataset: InterX-350 Silver Benchmark, pre-governance source state
- Raw records: 351 lines / 350 unique IDs
- Worker metadata: `{'unrecorded': 217, '3': 133}`
- KG: enabled; built from all 350 QA evidence references
- Reload: per-answer in application, but disabled by the multi-worker runner

## Preserved headline observations

- Chunk Hit@1: 0.6213
- Chunk Hit@5: 0.8383
- MRR: 0.7139
- P50/P95: 43.0s / 113.8s
- Router empty returns: 242 / 350

## Why this is diagnostic only

The source references were Silver, ID 65 was misbound, the answer Judge was not
schema-compatible, the KG used evaluation QA evidence, and timing conditions were
mixed. Retrieval Hit@K remains useful diagnostic evidence because capture occurred
before KG expansion, but this run is not the formal comparator for later claims.

See `manifest.json` for hashes and the complete limitation list.
