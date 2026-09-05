from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest

from baseline_v1_common import load_jsonl, sha256_file, write_json, write_jsonl
from build_verified_gold_v1 import build
from gold_verification_common import (
    CANDIDATE_COMMIT,
    PROHIBITED_REVIEW_KEYS,
    csv_to_record,
    load_chunk_levels,
    recursive_keys,
    remap_source_record,
    resolve_candidate_source_evidence,
    write_review_csv,
)
from seal_heldout_gold import seal
from validate_human_gold_review import REQUIRED_RECORD_KEYS, validate_record, validate_records


ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "evaluation/gold_verification/v1"


def records(split: str) -> list[dict]:
    return load_jsonl(VERIFY / split / "review_records.jsonl")


def test_review_ids_exactly_match_frozen_splits_and_do_not_overlap():
    actual = {split: {row["id"] for row in records(split)} for split in ("dev", "heldout")}
    expected = {
        split: {row["id"] for row in load_jsonl(ROOT / f"evaluation/splits/v1/{split}.jsonl")}
        for split in ("dev", "heldout")
    }
    assert actual == expected
    assert len(actual["dev"]) == 54
    assert len(actual["heldout"]) == 53
    assert actual["dev"].isdisjoint(actual["heldout"])


def test_review_schema_contract_and_all_records_are_unreviewed():
    schema = json.loads((VERIFY / "schema/human_gold_review_v1.schema.json").read_text(encoding="utf-8"))
    assert set(schema["required"]) == REQUIRED_RECORD_KEYS
    for row in records("dev") + records("heldout"):
        assert validate_record(row) == []
        assert row["human_review"]["review_status"] == "UNREVIEWED"
        assert row["human_review"]["overall_decision"] is None
        assert all(
            value is None
            for key, value in row["human_review"].items()
            if key != "review_status"
        )
        assert row["source_provenance"]["candidate_commit"] == CANDIDATE_COMMIT


def test_no_runtime_output_leaks_into_review_sheets_or_items():
    for split in ("dev", "heldout"):
        assert not (recursive_keys(records(split)) & PROHIBITED_REVIEW_KEYS)
        csv_path = VERIFY / split / f"{split.upper()}_GOLD_REVIEW.csv"
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            headers = set(next(csv.reader(handle)))
        assert not (headers & PROHIBITED_REVIEW_KEYS)
        text_paths = [VERIFY / split / f"{split.upper()}_GOLD_REVIEW.md", *(VERIFY / split / "items").glob("*.md")]
        for path in text_paths:
            lowered = path.read_text(encoding="utf-8").lower()
            assert all(key not in lowered for key in PROHIBITED_REVIEW_KEYS), path


def test_source_evidence_resolver_uses_exact_original_manual_lines():
    answer = {
        "content": "Use the first supported instruction.",
        "evidence_refs": [{"source": "data/en-manual/Color E-Reader.md", "lines": "1-2", "summary": "proposal"}],
    }
    expected = (ROOT / "data/en-manual/Color E-Reader.md").read_text(encoding="utf-8").splitlines()[:2]
    resolved = resolve_candidate_source_evidence(answer, {}, "en")
    assert resolved[0]["evidence_text"] == "\n".join(expected).strip()
    assert resolved[0]["resolution_method"] == "source_reference_line_span"
    unresolved = resolve_candidate_source_evidence(
        {"content": "x", "evidence_refs": [{"source": "missing.md", "lines": "1-2"}]}, {}, "en"
    )
    assert unresolved[0]["resolution_status"] == "UNRESOLVED"
    assert unresolved[0]["evidence_text"] is None


def test_csv_roundtrip_preserves_candidate_and_human_fields(tmp_path):
    source = deepcopy(records("dev")[0])
    source["human_review"]["review_status"] = "IN_PROGRESS"
    source["human_review"]["reviewer_notes"] = "checking source"
    path = tmp_path / "review.csv"
    write_review_csv(path, [source])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        restored = csv_to_record(next(csv.DictReader(handle)))
    assert restored["source_provenance"] == source["source_provenance"]
    assert restored["candidate_source_evidence"] == source["candidate_source_evidence"]
    assert restored["human_review"]["review_status"] == "IN_PROGRESS"
    assert restored["human_review"]["reviewer_notes"] == "checking source"


def approved_record(split: str = "dev") -> dict:
    row = deepcopy(records(split)[0])
    row["split"] = split
    row["human_review"].update({
        "review_status": "COMPLETED",
        "question_valid": True,
        "reference_answer_status": "APPROVE",
        "required_facts_status": "APPROVE",
        "source_evidence_status": "APPROVE",
        "image_status": "N/A" if not row["candidate_gold_images"] else "APPROVE",
        "chunk_mapping_status": "APPROVE",
        "overall_decision": "APPROVE",
        "reviewer_id": "human-reviewer",
        "reviewed_at": "2026-09-05T00:00:00Z",
    })
    return row


def test_review_validator_enforces_decision_requirements():
    row = approved_record()
    assert validate_record(row) == []
    row["human_review"]["reference_answer_status"] = None
    assert any("reference_answer_status" in error for error in validate_record(row))
    quarantine = approved_record()
    quarantine["human_review"]["overall_decision"] = "QUARANTINE"
    quarantine["human_review"]["quarantine_reason"] = None
    assert any("quarantine_reason" in error for error in validate_record(quarantine))
    assert validate_records(records("dev"), require_complete=False)["status"] == "PASS"
    assert validate_records(records("dev"), require_complete=True)["status"] == "FAIL"


def test_verified_builder_emits_only_human_approved_and_refuses_incomplete_final(tmp_path):
    dev_input = tmp_path / "dev.jsonl"
    heldout_input = tmp_path / "heldout.jsonl"
    write_jsonl(dev_input, [approved_record("dev")])
    write_jsonl(heldout_input, [approved_record("heldout")])
    manifest = build({"dev": dev_input, "heldout": heldout_input}, tmp_path / "final", preview=False)
    assert manifest["human_verification_complete"] is True
    gold = load_jsonl(tmp_path / "final/dev_gold.jsonl")
    assert len(gold) == 1 and gold[0]["quality_status"] == "human_verified"
    write_jsonl(dev_input, [records("dev")[0]])
    with pytest.raises(ValueError, match="validation failed"):
        build({"dev": dev_input, "heldout": heldout_input}, tmp_path / "refused", preview=False)
    preview = build({"dev": dev_input, "heldout": heldout_input}, tmp_path / "preview", preview=True)
    assert preview["human_verification_complete"] is False
    assert load_jsonl(tmp_path / "preview/dev_gold.preview.jsonl") == []


def test_heldout_seal_requires_ack_and_complete_final_build(tmp_path):
    dev_input = tmp_path / "dev.jsonl"
    heldout_input = tmp_path / "heldout.jsonl"
    write_jsonl(dev_input, [approved_record("dev")])
    write_jsonl(heldout_input, [approved_record("heldout")])
    final_dir = tmp_path / "final"
    build({"dev": dev_input, "heldout": heldout_input}, final_dir, preview=False)
    with pytest.raises(ValueError, match="acknowledge"):
        seal(final_dir / "heldout_gold.jsonl", final_dir / "MANIFEST.json", tmp_path / "seal", acknowledged=False)
    manifest = seal(final_dir / "heldout_gold.jsonl", final_dir / "MANIFEST.json", tmp_path / "seal", acknowledged=True)
    assert manifest["sealed"] is True
    assert manifest["gold_hash"] == sha256_file(final_dir / "heldout_gold.jsonl")


def test_chunk_remap_uses_line_overlap_and_can_leave_unresolved():
    chunks = load_chunk_levels()
    row = next(
        row for row in records("dev")
        if row["candidate_chunk_mapping"]["mapping_status"] == "PROPOSED_RESOLVED"
    )
    mapped = remap_source_record(row, chunks, corpus_hash="test-corpus")
    assert mapped["mapping_method"] == "manual_identity_and_source_line_overlap"
    assert mapped["acceptable_small_chunk_ids"]
    bad = deepcopy(row)
    bad["candidate_source_evidence"] = [{
        "evidence_id": "E1", "manual_id": "does-not-exist", "manual_title": "does-not-exist",
        "source_lines": [{"start": 1, "end": 1}], "source_location": "missing:1-1",
        "resolution_status": "PROPOSED_SOURCE_SPAN_RESOLVED",
    }]
    unresolved = remap_source_record(bad, chunks, corpus_hash="test-corpus")
    assert unresolved["mapping_status"] == "CHUNK_MAPPING_UNRESOLVED"
