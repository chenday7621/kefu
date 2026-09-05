#!/usr/bin/env python3
"""Remap proposed/verified source spans to a chunk corpus by deterministic overlap."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from baseline_v1_common import ROOT, load_jsonl, sha256_tree, write_json, write_jsonl
from gold_verification_common import load_chunk_levels, remap_source_record


def remap_records(records: list[dict], corpus_dir: Path) -> tuple[list[dict], dict]:
    chunks = load_chunk_levels(corpus_dir)
    corpus_hash = sha256_tree(corpus_dir)
    output = []
    for record in records:
        updated = dict(record)
        mapping = remap_source_record(record, chunks, corpus_hash=corpus_hash)
        if "candidate_source_evidence" in record:
            updated["candidate_chunk_mapping"] = mapping
        else:
            updated["retrieval_mapping"] = mapping
        output.append(updated)
    resolved = sum(
        (row.get("candidate_chunk_mapping") or row.get("retrieval_mapping"))["mapping_status"] == "PROPOSED_RESOLVED"
        for row in output
    )
    return output, {
        "schema_version": "interx-source-gold-chunk-remap-v1",
        "mapping_policy": "manual identity and source-line overlap only; semantic similarity is prohibited",
        "corpus_hash": corpus_hash,
        "input_count": len(records),
        "resolved_count": resolved,
        "unresolved_or_partial_count": len(records) - resolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "process/artifacts/manuals")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    records, manifest = remap_records(load_jsonl(args.input), args.corpus_dir)
    write_jsonl(args.output, records)
    write_json(args.manifest or args.output.with_suffix(".manifest.json"), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
