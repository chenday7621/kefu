#!/usr/bin/env python3
"""Create an immutable-reference manifest for the preserved Phase1 diagnostic run."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_jsonl, sha256_file, write_json  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    source = ROOT / "evaluation" / "results" / "baseline350"
    target = ROOT / "evaluation" / "baselines" / "phase1_diagnostic"
    target.mkdir(parents=True, exist_ok=True)
    prior_manifest_path = target / "manifest.json"
    prior_manifest = (
        json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        if prior_manifest_path.exists() else {}
    )

    files = [source / "raw.jsonl", source / "metrics.json", source / "run_manifest_from_baseline50.json"]
    legacy_gold = ROOT / "evaluation" / "gold" / "gold.jsonl"
    legacy_gold_config = ROOT / "evaluation" / "gold" / "gold_build_config.json"
    for path in (legacy_gold, legacy_gold_config):
        if path.exists():
            copied = target / f"phase1_{path.name}"
            if not copied.exists():
                shutil.copy2(path, copied)

    rows = load_jsonl(source / "raw.jsonl")
    latest = {str(row["id"]): row for row in rows}
    worker_counts = Counter(str(row.get("workers", "unrecorded")) for row in latest.values())
    manifest = {
        "baseline_name": "Phase1 Diagnostic Baseline",
        "frozen_at": prior_manifest.get("frozen_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "tags_at_commit": git("tag", "--points-at", "HEAD").splitlines(),
        "dataset_name": "InterX-350 Silver Benchmark (pre-V1 source state)",
        "run_date": "2026-07-17",
        "model_aliases": {
            "answer_router": "qwen3.6-plus",
            "answer_rewrite_judge": "qwen3-max",
            "upstream_at_run": "openai/deepseek-v4-flash",
            "embedding": "qwen3-vl-embedding",
            "reranker": "qwen3-rerank",
        },
        "worker_field_counts": dict(sorted(worker_counts.items())),
        "kg": {"enabled": True, "source": "all 350 QA evidence_refs (leaking for answer evaluation)"},
        "reload": {
            "per_answer_in_application": True,
            "multi_worker_runner_override": "load once then no-op",
            "consistent_across_records": False,
        },
        "known_issues": [
            "InterX-350 answers are Agent-generated Silver references, not authoritative Gold.",
            "ID 65 question/answer mismatch in the pre-V1 source data.",
            "KG was built from all 350 QA evidence references.",
            "run_judge.py was incompatible with the generated reference schema and was not run.",
            "recall_meta.elapsed_seconds combined router/reload/rewrite/decompose/retrieval/KG.",
            "runtime records used mixed or unrecorded concurrency/reload conditions.",
            "raw.jsonl contains retries; metric readers keep the last record per ID.",
        ],
        "artifacts": {},
    }
    for path in files + [target / "phase1_gold.jsonl", target / "phase1_gold_build_config.json"]:
        if path.exists():
            manifest["artifacts"][path.relative_to(ROOT).as_posix()] = {
                "sha256": sha256_file(path), "bytes": path.stat().st_size
            }
    write_json(target / "manifest.json", manifest)

    metrics = json.loads((source / "metrics.json").read_text(encoding="utf-8"))["summary"]
    text = f"""# Phase1 Diagnostic Baseline (preserved)

This document freezes the provenance of the pre-V1 run. It does not modify or
replace `evaluation/results/baseline350/`.

- Commit: `{manifest['commit']}`
- Tag at commit: `{', '.join(manifest['tags_at_commit'])}`
- Run date: 2026-07-17
- Dataset: InterX-350 Silver Benchmark, pre-governance source state
- Raw records: {len(rows)} lines / {len(latest)} unique IDs
- Worker metadata: `{dict(worker_counts)}`
- KG: enabled; built from all 350 QA evidence references
- Reload: per-answer in application, but disabled by the multi-worker runner

## Preserved headline observations

- Chunk Hit@1: {metrics['retrieval_chunk_gold']['hit@1']['mean']}
- Chunk Hit@5: {metrics['retrieval_chunk_gold']['hit@5']['mean']}
- MRR: {metrics['retrieval_chunk_gold']['mrr']['mean']}
- P50/P95: {metrics['runtime']['p50_s']}s / {metrics['runtime']['p95_s']}s
- Router empty returns: {metrics['router']['empty_return']} / {metrics['router']['calls']}

## Why this is diagnostic only

The source references were Silver, ID 65 was misbound, the answer Judge was not
schema-compatible, the KG used evaluation QA evidence, and timing conditions were
mixed. Retrieval Hit@K remains useful diagnostic evidence because capture occurred
before KG expansion, but this run is not the formal comparator for later claims.

See `manifest.json` for hashes and the complete limitation list.
"""
    (ROOT / "evaluation" / "baselines" / "PHASE1_DIAGNOSTIC_BASELINE.md").write_text(text, encoding="utf-8")
    print(target / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
