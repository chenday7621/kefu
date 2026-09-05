#!/usr/bin/env python3
"""Dependency-free semantic validation for InterX Reference Schema V2."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_chunk_index, load_jsonl  # noqa: E402


REQUIRED = {
    "id", "question", "language", "quality_status", "reference_answer", "evidence",
    "gold_chunk_ids", "gold_docs", "gold_images", "source_provenance", "coverage", "split",
}
EVIDENCE_REQUIRED = {"chunk_id", "text", "manual_id", "section", "source_location", "resolution_status"}


def validate(records: list[dict], chunk_ids: set[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(records, 1):
        missing = REQUIRED - set(row)
        if missing:
            errors.append(f"record {index}: missing {sorted(missing)}")
            continue
        qid = str(row["id"])
        if qid in seen:
            errors.append(f"record {index}: duplicate id {qid}")
        seen.add(qid)
        if row["language"] not in {"zh", "en"}:
            errors.append(f"id {qid}: invalid language")
        if row["quality_status"] not in {"silver", "verified", "quarantined"}:
            errors.append(f"id {qid}: invalid quality_status")
        if row["split"] not in {"train", "dev", "heldout", "quarantined"}:
            errors.append(f"id {qid}: invalid split")
        if not isinstance(row["evidence"], list) or not row["evidence"]:
            errors.append(f"id {qid}: evidence must be a non-empty list")
        for evidence in row["evidence"]:
            if EVIDENCE_REQUIRED - set(evidence):
                errors.append(f"id {qid}: malformed evidence entry")
            cid = evidence.get("chunk_id")
            if cid and cid not in chunk_ids:
                errors.append(f"id {qid}: missing corpus chunk {cid}")
            if evidence.get("resolution_status") in {"chunk_resolved", "source_resolved"} and not evidence.get("text"):
                errors.append(f"id {qid}: resolved evidence has no text")
        if bool(row["gold_chunk_ids"]) != bool(row["coverage"]["chunk"]):
            errors.append(f"id {qid}: chunk coverage mismatch")
        if len(row["gold_chunk_ids"]) != len(set(row["gold_chunk_ids"])):
            errors.append(f"id {qid}: duplicate gold chunk IDs")
    return errors


def main() -> int:
    records = load_jsonl(ROOT / "evaluation" / "gold_v2" / "references.jsonl")
    errors = validate(records, set(load_chunk_index()))
    status = {"status": "pass" if not errors else "fail", "records": len(records), "errors": errors}
    (ROOT / "evaluation/gold_v2/validation.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
