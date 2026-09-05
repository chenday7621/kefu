from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from baseline_v1_common import load_chunk_index, load_jsonl, sha256_file
from validate_gold_v2 import validate
from process_chunk.config import ProcessSettings


ROOT = Path(__file__).resolve().parents[2]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_dataset_audit_all_350_and_known_repairs():
    audit = read_json("evaluation/audits/dataset_governance_v1.json")
    summary = audit["summary"]
    assert summary["record_count"] == 350
    assert not summary["duplicate_question_ids"]
    assert not summary["duplicate_answer_ids"]
    assert not summary["missing_question_ids"]
    assert not summary["missing_answer_ids"]
    assert summary["error_counts"] == {}
    by_id = {str(row["id"]): row for row in audit["records"]}
    assert by_id["65"]["quality_status"] == "verified"
    assert "吹风机" in by_id["65"]["question"]
    assert by_id["305"]["quality_status"] == "silver"
    assert by_id["305"]["question_answer_text_aligned"] is True


def test_gold_v2_schema_and_evidence_resolution():
    rows = load_jsonl(ROOT / "evaluation/gold_v2/references.jsonl")
    errors = validate(rows, set(load_chunk_index()))
    assert errors == []
    assert len(rows) == 350
    assert sum(row["coverage"]["evidence_text"] for row in rows) == 250
    for row in rows:
        for evidence in row["evidence"]:
            if evidence["resolution_status"] in {"chunk_resolved", "source_resolved"}:
                assert evidence["text"]


def test_split_reproducibility_and_no_overlap():
    manifest_path = ROOT / "evaluation/splits/v1/split_manifest.json"
    before = read_json("evaluation/splits/v1/split_manifest.json")
    subprocess.run([sys.executable, str(ROOT / "evaluation/scripts/make_splits_v1.py")], check=True)
    after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert before["split_hash"] == after["split_hash"]
    assert before["id_hashes"] == after["id_hashes"]
    split_ids = {
        split: {str(row["id"]) for row in load_jsonl(ROOT / f"evaluation/splits/v1/{split}.jsonl")}
        for split in ("train", "dev", "heldout", "quarantined")
    }
    names = list(split_ids)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            assert split_ids[left].isdisjoint(split_ids[right])
    assert sum(map(len, split_ids.values())) == 350
    assert all(not values for values in after["manual_group_overlap"].values())


def test_manifest_uses_logical_corpus_hash_not_physical_milvus_bytes():
    manifest = read_json("evaluation/baselines/baseline_v1_environment_manifest.json")
    parts = manifest["hashes"]["corpus_parts"]
    assert manifest["hashes"]["corpus"] == parts["manual_artifacts_tree"]
    assert "milvus_lite_physical_tree_noncanonical" in parts


def test_kg_qa_sources_are_train_only_and_runtime_disabled():
    manifest = read_json("kg/state/v1_train_only/build_manifest.json")
    assert manifest["split_source"] == "train-only"
    assert manifest["leakage_status"] == "pass"
    assert manifest["dev_answer_id_overlap"] == []
    assert manifest["heldout_answer_id_overlap"] == []
    config = (ROOT / "answer/configs/baseline_v1.yaml").read_text(encoding="utf-8")
    assert "kg:\n  enabled: false" in config
    train = {str(row["id"]) for row in load_jsonl(ROOT / "evaluation/splits/v1/train.jsonl")}
    mapped = read_json("kg/state/v1_train_only/evidence_mapped.json")
    semantic = read_json("kg/state/v1_train_only/semantic_edges.json")
    assert {str(row["answer_id"]) for row in mapped["records"]} <= train
    assert {str(row["answer_id"]) for row in semantic["edges"]} <= train


def test_phase1_raw_artifact_is_preserved_by_hash():
    manifest = read_json("evaluation/baselines/phase1_diagnostic/manifest.json")
    raw = ROOT / "evaluation/results/baseline350/raw.jsonl"
    expected = manifest["artifacts"]["evaluation/results/baseline350/raw.jsonl"]["sha256"]
    assert sha256_file(raw) == expected


def test_heldout_runner_requires_explicit_acknowledgement(tmp_path):
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "evaluation/scripts/run_baseline.py"),
            "--out", str(tmp_path / "raw.jsonl"),
            "--split-file", "evaluation/splits/v1/heldout.jsonl",
            "--limit", "1",
        ],
        text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "requires --ack-heldout" in (result.stdout + result.stderr)


def test_process_default_path_discovers_bilingual_manuals():
    files = ProcessSettings.load().manual_files()
    assert len(files) == 40
    assert sum("ch-manual" in path.as_posix() for path in files) == 20
    assert sum("en-manual" in path.as_posix() for path in files) == 20
