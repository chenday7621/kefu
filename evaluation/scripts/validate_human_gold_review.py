#!/usr/bin/env python3
"""Validate Human Gold review records without making or inferring decisions."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from baseline_v1_common import ROOT, write_json
from gold_verification_common import (
    CANDIDATE_COMMIT,
    OVERALL_DECISIONS,
    PROHIBITED_REVIEW_KEYS,
    SCHEMA_VERSION,
    SPLITS,
    load_review_records,
    recursive_keys,
)


REQUIRED_RECORD_KEYS = {
    "schema_version", "id", "split", "language", "question",
    "candidate_reference_answer", "candidate_required_facts",
    "candidate_optional_facts", "candidate_forbidden_claims",
    "candidate_source_evidence", "candidate_gold_images",
    "candidate_chunk_mapping", "candidate_resolution_status",
    "automatic_warnings", "source_provenance", "human_review",
}
REQUIRED_HUMAN_KEYS = {
    "review_status", "question_valid", "reference_answer_status",
    "reference_answer_final", "required_facts_status", "required_facts_final",
    "source_evidence_status", "source_evidence_final",
    "source_evidence_unresolved_reason", "image_status", "image_final",
    "chunk_mapping_status", "chunk_mapping_final", "overall_decision",
    "quarantine_reason", "reviewer_notes", "reviewer_id", "reviewed_at",
}


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def validate_record(record: dict[str, Any], *, require_complete: bool = False) -> list[str]:
    errors: list[str] = []
    qid = str(record.get("id") or "<missing>")
    missing = sorted(REQUIRED_RECORD_KEYS - set(record))
    if missing:
        errors.append(f"{qid}: missing record fields: {missing}")
        return errors
    prohibited = sorted(PROHIBITED_REVIEW_KEYS & recursive_keys(record))
    if prohibited:
        errors.append(f"{qid}: prohibited runtime-output fields: {prohibited}")
    if record["schema_version"] != SCHEMA_VERSION:
        errors.append(f"{qid}: unexpected schema_version={record['schema_version']!r}")
    if record["split"] not in SPLITS:
        errors.append(f"{qid}: invalid split={record['split']!r}")
    if record["language"] not in {"zh", "en"}:
        errors.append(f"{qid}: invalid language={record['language']!r}")
    if not _nonempty(record["question"]):
        errors.append(f"{qid}: question is empty")
    if not isinstance(record["candidate_source_evidence"], list):
        errors.append(f"{qid}: candidate_source_evidence must be a list")
    if not isinstance(record["candidate_required_facts"], list):
        errors.append(f"{qid}: candidate_required_facts must be a list")
    for index, fact in enumerate(record.get("candidate_required_facts") or []):
        if fact.get("machine_proposed") is not True:
            errors.append(f"{qid}: candidate fact {index} is not marked machine_proposed")
        if not _nonempty(fact.get("text")):
            errors.append(f"{qid}: candidate fact {index} has no text")
    for index, evidence in enumerate(record.get("candidate_source_evidence") or []):
        if evidence.get("machine_proposed") is not True:
            errors.append(f"{qid}: candidate evidence {index} is not marked machine_proposed")
        if evidence.get("resolution_status") == "PROPOSED_SOURCE_SPAN_RESOLVED":
            if not _nonempty(evidence.get("evidence_text")) or not evidence.get("source_lines"):
                errors.append(f"{qid}: proposed resolved evidence {index} lacks text or source lines")
    provenance = record.get("source_provenance") or {}
    if provenance.get("candidate_commit") != CANDIDATE_COMMIT:
        errors.append(f"{qid}: candidate_commit provenance mismatch")

    human = record.get("human_review")
    if not isinstance(human, dict):
        errors.append(f"{qid}: human_review must be an object")
        return errors
    missing_human = sorted(REQUIRED_HUMAN_KEYS - set(human))
    if missing_human:
        errors.append(f"{qid}: missing human-review fields: {missing_human}")
        return errors
    decision = human.get("overall_decision")
    if decision is not None and decision not in OVERALL_DECISIONS:
        errors.append(f"{qid}: invalid overall_decision={decision!r}")
    if decision is None:
        if require_complete:
            errors.append(f"{qid}: human review is incomplete")
        return errors
    if human.get("review_status") != "COMPLETED":
        errors.append(f"{qid}: decision exists but review_status is not COMPLETED")
    if not _nonempty(human.get("reviewer_id")) or not _nonempty(human.get("reviewed_at")):
        errors.append(f"{qid}: completed decision requires reviewer_id and reviewed_at")
    if decision == "APPROVE":
        if human.get("question_valid") is not True:
            errors.append(f"{qid}: APPROVE requires question_valid=true")
        if human.get("reference_answer_status") != "APPROVE":
            errors.append(f"{qid}: APPROVE requires reference_answer_status=APPROVE")
        if human.get("required_facts_status") != "APPROVE":
            errors.append(f"{qid}: APPROVE requires required_facts_status=APPROVE")
        if human.get("source_evidence_status") not in {"APPROVE", "N/A"}:
            errors.append(f"{qid}: APPROVE requires approved or explicitly N/A source evidence")
        if human.get("image_status") not in {"APPROVE", "N/A"}:
            errors.append(f"{qid}: APPROVE requires image_status APPROVE or N/A")
        if human.get("chunk_mapping_status") not in {"APPROVE", "UNRESOLVED_ACCEPTED"}:
            errors.append(f"{qid}: APPROVE requires reviewed chunk mapping status")
    elif decision == "EDITED_APPROVE":
        if human.get("question_valid") is not True:
            errors.append(f"{qid}: EDITED_APPROVE requires question_valid=true")
        if human.get("reference_answer_status") != "EDIT" or not _nonempty(human.get("reference_answer_final")):
            errors.append(f"{qid}: EDITED_APPROVE requires edited final reference answer")
        if human.get("required_facts_status") != "EDIT" or not _nonempty(human.get("required_facts_final")):
            errors.append(f"{qid}: EDITED_APPROVE requires edited final required facts")
        has_final_evidence = _nonempty(human.get("source_evidence_final"))
        has_unresolved_reason = _nonempty(human.get("source_evidence_unresolved_reason"))
        if human.get("source_evidence_status") != "EDIT" or not (has_final_evidence or has_unresolved_reason):
            errors.append(f"{qid}: EDITED_APPROVE requires final evidence or a legal unresolved reason")
        if human.get("image_status") not in {"APPROVE", "EDIT", "N/A"}:
            errors.append(f"{qid}: EDITED_APPROVE requires reviewed image status")
        if human.get("chunk_mapping_status") not in {"APPROVE", "EDIT", "UNRESOLVED_ACCEPTED"}:
            errors.append(f"{qid}: EDITED_APPROVE requires reviewed chunk mapping status")
    elif decision == "QUARANTINE":
        if not _nonempty(human.get("quarantine_reason")):
            errors.append(f"{qid}: QUARANTINE requires quarantine_reason")
    elif decision == "NEEDS_SECOND_REVIEW":
        if not _nonempty(human.get("reviewer_notes")):
            errors.append(f"{qid}: NEEDS_SECOND_REVIEW requires reviewer_notes")
        if require_complete:
            errors.append(f"{qid}: NEEDS_SECOND_REVIEW is not eligible for completed Gold")
    return errors


def validate_records(records: list[dict[str, Any]], *, require_complete: bool = False) -> dict[str, Any]:
    errors = [error for record in records for error in validate_record(record, require_complete=require_complete)]
    ids = [str(record.get("id")) for record in records]
    duplicates = sorted(qid for qid, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate record IDs: {duplicates}")
    decisions = Counter((record.get("human_review") or {}).get("overall_decision") or "UNREVIEWED" for record in records)
    return {
        "status": "PASS" if not errors else "FAIL",
        "record_count": len(records),
        "require_complete": require_complete,
        "decision_counts": dict(sorted(decisions.items())),
        "eligible_count": sum(decisions[value] for value in ("APPROVE", "EDITED_APPROVE")),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    records = load_review_records(args.input)
    report = validate_records(records, require_complete=args.require_complete)
    if args.report:
        write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
