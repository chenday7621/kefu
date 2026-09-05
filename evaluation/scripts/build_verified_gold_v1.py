#!/usr/bin/env python3
"""Build Human-Verified Gold only from explicit, valid human decisions."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baseline_v1_common import ROOT, numeric_key, sha256_records, write_json, write_jsonl
from gold_verification_common import CANDIDATE_COMMIT, SPLITS, data_hashes, load_review_records
from validate_human_gold_review import validate_records


def final_value(
    record: dict[str, Any],
    candidate_key: str,
    final_key: str,
    status_key: str,
) -> Any:
    human = record["human_review"]
    return human.get(final_key) if human.get(status_key) == "EDIT" else record[candidate_key]


def verified_record(record: dict[str, Any]) -> dict[str, Any]:
    human = record["human_review"]
    evidence = final_value(
        record, "candidate_source_evidence", "source_evidence_final", "source_evidence_status"
    )
    if human["overall_decision"] == "EDITED_APPROVE" and evidence is None:
        evidence = []
    return {
        "schema_version": "interx-human-verified-gold-v1",
        "id": record["id"],
        "split": record["split"],
        "language": record["language"],
        "question": record["question"],
        "quality_status": "human_verified",
        "source_gold": evidence,
        "semantic_gold": {
            "reference_answer": final_value(
                record, "candidate_reference_answer", "reference_answer_final", "reference_answer_status"
            ),
            "required_facts": final_value(
                record, "candidate_required_facts", "required_facts_final", "required_facts_status"
            ),
            "optional_facts": record["candidate_optional_facts"],
            "forbidden_claims": record["candidate_forbidden_claims"],
            "answer_notes": human.get("reviewer_notes"),
        },
        "retrieval_mapping": final_value(
            record, "candidate_chunk_mapping", "chunk_mapping_final", "chunk_mapping_status"
        ),
        "images": final_value(record, "candidate_gold_images", "image_final", "image_status"),
        "human_verification": {
            "decision": human["overall_decision"],
            "reviewer_id": human["reviewer_id"],
            "reviewed_at": human["reviewed_at"],
        },
        "source_provenance": record["source_provenance"],
    }


def build(inputs: dict[str, Path], output_dir: Path, *, preview: bool) -> dict[str, Any]:
    all_records = {split: load_review_records(path) for split, path in inputs.items()}
    reports = {split: validate_records(rows, require_complete=not preview) for split, rows in all_records.items()}
    invalid = {split: report["errors"] for split, report in reports.items() if report["status"] != "PASS"}
    if invalid:
        raise ValueError("review validation failed: " + json.dumps(invalid, ensure_ascii=False))
    complete = all(
        all(row["human_review"]["overall_decision"] in {"APPROVE", "EDITED_APPROVE", "QUARANTINE"} for row in rows)
        for rows in all_records.values()
    )
    if not preview and not complete:
        raise ValueError("final Human-Verified Gold build refused: human verification is incomplete")

    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = data_hashes()
    manifest: dict[str, Any] = {
        "schema_version": "interx-human-verified-gold-build-v1",
        "mode": "PARTIAL_PREVIEW" if preview else "FINAL",
        "human_verification_complete": bool(complete and not preview),
        "candidate_commit": CANDIDATE_COMMIT,
        "created_at": None if preview else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hashes": hashes,
        "splits": {},
    }
    for split, rows in all_records.items():
        approved = [verified_record(row) for row in rows if row["human_review"]["overall_decision"] in {"APPROVE", "EDITED_APPROVE"}]
        approved.sort(key=lambda row: numeric_key(row["id"]))
        quarantined = [row["id"] for row in rows if row["human_review"]["overall_decision"] == "QUARANTINE"]
        pending = [row["id"] for row in rows if row["human_review"]["overall_decision"] not in {"APPROVE", "EDITED_APPROVE", "QUARANTINE"}]
        name = f"{split}_gold.preview.jsonl" if preview else f"{split}_gold.jsonl"
        write_jsonl(output_dir / name, approved)
        manifest["splits"][split] = {
            "input_count": len(rows),
            "verified_count": len(approved),
            "quarantined_ids": quarantined,
            "pending_ids": pending,
            "output": name,
            "output_hash": sha256_records(approved),
        }
    write_json(output_dir / "MANIFEST.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--dev-input", type=Path, default=ROOT / "evaluation/gold_verification/v1/dev/DEV_GOLD_REVIEW.csv")
    parser.add_argument("--heldout-input", type=Path, default=ROOT / "evaluation/gold_verification/v1/heldout/HELDOUT_GOLD_REVIEW.csv")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or ROOT / ("evaluation/gold_v1_preview" if args.preview else "evaluation/gold_v1")
    manifest = build({"dev": args.dev_input, "heldout": args.heldout_input}, output, preview=args.preview)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
