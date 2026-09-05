#!/usr/bin/env python3
"""Seal a completed Heldout Human-Verified Gold file with explicit acknowledgement."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from baseline_v1_common import ROOT, load_jsonl, sha256_file, write_json
from gold_verification_common import CANDIDATE_COMMIT, data_hashes


def seal(gold_path: Path, build_manifest_path: Path, output_dir: Path, *, acknowledged: bool) -> dict:
    if not acknowledged:
        raise ValueError("Heldout seal refused: pass --acknowledge-seal after human verification is complete")
    manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("mode") != "FINAL" or manifest.get("human_verification_complete") is not True:
        raise ValueError("Heldout seal refused: final build manifest is not human-verification complete")
    heldout = manifest.get("splits", {}).get("heldout") or {}
    if Path(str(heldout.get("output"))).name != gold_path.name:
        raise ValueError("Heldout seal refused: Gold filename does not match build manifest")
    expected_hash = heldout.get("output_hash")
    records = load_jsonl(gold_path)
    actual_hash = sha256_file(gold_path)
    # output_hash is the canonical records hash and equals the JSONL byte hash
    # because write_jsonl emits exactly one canonical record per line.
    if expected_hash != actual_hash:
        raise ValueError("Heldout seal refused: Gold hash does not match final build manifest")
    if any(row.get("quality_status") != "human_verified" for row in records):
        raise ValueError("Heldout seal refused: non-human-verified record present")
    reviewed_ids = [str(row["id"]) for row in records]
    quarantined_ids = [str(value) for value in heldout.get("quarantined_ids") or []]
    if heldout.get("pending_ids"):
        raise ValueError("Heldout seal refused: pending IDs remain")
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar = output_dir / "heldout_gold.sha256"
    sidecar.write_text(f"{actual_hash}  {gold_path.name}\n", encoding="utf-8")
    result = {
        "schema_version": "interx-heldout-gold-seal-v1",
        "sealed": True,
        "candidate_commit": CANDIDATE_COMMIT,
        "sealed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_hash": data_hashes()["dataset"],
        "split_hash": data_hashes()["split"],
        "source_corpus_hash": data_hashes()["source_corpus"],
        "gold_hash": actual_hash,
        "reviewed_ids": reviewed_ids,
        "quarantined_ids": quarantined_ids,
        "development_policy": "Do not use Heldout runtime outputs or errors for prompt, parameter, or algorithm development.",
    }
    write_json(output_dir / "HELDOUT_GOLD_MANIFEST.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=ROOT / "evaluation/gold_v1/heldout_gold.jsonl")
    parser.add_argument("--build-manifest", type=Path, default=ROOT / "evaluation/gold_v1/MANIFEST.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/gold_v1")
    parser.add_argument("--acknowledge-seal", action="store_true")
    args = parser.parse_args()
    result = seal(args.gold, args.build_manifest, args.output_dir, acknowledged=args.acknowledge_seal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
