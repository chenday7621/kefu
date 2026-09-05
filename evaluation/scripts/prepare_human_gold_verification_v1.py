#!/usr/bin/env python3
"""Prepare proposed Dev/Heldout review assets without making human decisions."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from baseline_v1_common import ROOT, load_jsonl, numeric_key, sha256_file, sha256_records, write_json, write_jsonl
from gold_verification_common import (
    CANDIDATE_COMMIT,
    PROHIBITED_REVIEW_KEYS,
    RESOLVED_EVIDENCE_STATUSES,
    SCHEMA_VERSION,
    SPLITS,
    add_duplicate_warnings,
    data_hashes,
    empty_human_review,
    load_chunk_levels,
    proposed_images,
    propose_required_facts,
    record_warnings,
    recursive_keys,
    remap_source_record,
    resolve_candidate_source_evidence,
    source_inputs_hash,
    warning_summary,
    write_review_csv,
)


OUTPUT_ROOT = ROOT / "evaluation/gold_verification/v1"


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def ensure_candidate_ancestry() -> str:
    head = git_output("rev-parse", "HEAD")
    subprocess.check_call(
        ["git", "merge-base", "--is-ancestor", CANDIDATE_COMMIT, head],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    return head


def resolution_status(evidence: list[dict[str, Any]], facts: list[dict[str, Any]], mapping: dict[str, Any]) -> str:
    resolved = sum(item.get("resolution_status") in RESOLVED_EVIDENCE_STATUSES for item in evidence)
    if not resolved:
        return "SOURCE_EVIDENCE_UNRESOLVED"
    if resolved < len(evidence) or mapping["mapping_status"] != "PROPOSED_RESOLVED" or not facts:
        return "PROPOSED_PARTIAL"
    return "PROPOSED_RESOLVED"


def build_record(
    split: str,
    reference: dict[str, Any],
    split_row: dict[str, Any],
    answer: dict[str, Any],
    chunks: dict[str, list[dict[str, Any]]],
    hashes: dict[str, str],
) -> dict[str, Any]:
    language = str(reference["language"])
    evidence = resolve_candidate_source_evidence(answer, reference, language)
    facts = propose_required_facts(str(reference.get("reference_answer") or ""), evidence, language)
    temporary = {"candidate_source_evidence": evidence}
    mapping = remap_source_record(temporary, chunks, corpus_hash=hashes["source_corpus"])
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": str(reference["id"]),
        "split": split,
        "language": language,
        "question": str(reference["question"]),
        "candidate_reference_answer": str(reference.get("reference_answer") or ""),
        "candidate_required_facts": facts,
        "candidate_optional_facts": [],
        "candidate_forbidden_claims": [],
        "candidate_source_evidence": evidence,
        "candidate_gold_images": proposed_images(reference),
        "candidate_chunk_mapping": mapping,
        "candidate_resolution_status": resolution_status(evidence, facts, mapping),
        "automatic_warnings": [],
        "source_provenance": {
            "dataset_name": "InterX-350 Silver Benchmark",
            "candidate_commit": CANDIDATE_COMMIT,
            "foundation_source_commit": CANDIDATE_COMMIT,
            "source_question_id": str(split_row.get("source_question_id") or reference["id"]),
            "source_answer_id": str(split_row.get("source_answer_id") or answer.get("id") or reference["id"]),
            "source_question_file": split_row.get("source_question_file"),
            "source_answer_file": split_row.get("source_answer_file") or answer.get("_source_path"),
            "silver_reference_v2_file": f"evaluation/gold_v2/{split}.jsonl",
            "source_evidence_policy": "original manual line spans first; current Candidate chunk source span only as explicit fallback; never infer with similarity",
            "required_facts_policy": "source-verbatim statements with conservative lexical overlap; machine proposal only",
            "chunk_mapping_policy": "manual identity plus source-line overlap only; no ranking, score, or semantic nearest-neighbor selection",
            "machine_proposed": True,
            "hashes": hashes,
        },
        "human_review": empty_human_review(),
    }
    expected_manuals = {str(v) for v in reference.get("gold_docs") or []}
    record["automatic_warnings"] = record_warnings(
        record,
        expected_manuals=expected_manuals,
        answer_source_id=str(answer.get("id") or ""),
        question_source_id=str(split_row.get("source_question_id") or reference["id"]),
    )
    return record


def render_item(record: dict[str, Any]) -> str:
    facts = record["candidate_required_facts"]
    evidence = record["candidate_source_evidence"]
    images = record["candidate_gold_images"]
    mapping = record["candidate_chunk_mapping"]
    warnings = record["automatic_warnings"]
    lines = [
        f"# Question {record['id']}", "",
        "> Status: machine-proposed review material; not Human-Verified Gold.", "",
        "## Question", "", record["question"], "",
        "## Candidate Silver Answer", "", record["candidate_reference_answer"] or "_Missing_", "",
        "## Candidate Required Facts", "",
    ]
    if facts:
        for index, fact in enumerate(facts, 1):
            lines.extend([
                f"{index}. {fact['text']}",
                f"   Source: `{', '.join(fact['source_evidence_ids'])}`; machine proposed.",
            ])
    else:
        lines.append("_No conservative proposal; human review required._")
    lines.extend(["", "## Source Manual Evidence", ""])
    for item in evidence:
        lines.extend([
            f"### {item['evidence_id']}: {item.get('manual_title') or 'Unresolved manual'}",
            "",
            f"- Resolution: `{item['resolution_status']}`",
            f"- Section: `{' > '.join(item.get('section_path') or []) or 'unavailable'}`",
            f"- Location: `{item.get('source_location') or 'unavailable'}`",
            f"- Method: `{item.get('resolution_method')}`",
            "",
        ])
        if item.get("evidence_text"):
            lines.extend(["```text", item["evidence_text"], "```", ""])
        else:
            lines.extend([f"_Unresolved: {item.get('unresolved_reason') or 'reason unavailable'}_", ""])
    lines.extend(["## Candidate Images", ""])
    if images:
        lines.extend(f"- `{item['image_id']}` — `{item['resolution_status']}` — `{item.get('source_path') or 'unavailable'}`" for item in images)
    else:
        lines.append("_N/A proposed; human confirmation required._")
    lines.extend(["", "## Candidate Source-based Chunk Mapping", ""])
    for level in ("small", "mid", "big"):
        ids = mapping[f"acceptable_{level}_chunk_ids"]
        lines.append(f"- {level}: {', '.join(f'`{value}`' for value in ids) if ids else '_unresolved_'}")
    lines.extend(["", "### Evidence Groups", "", "```json", json.dumps(mapping["evidence_groups"], ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Automatic Warnings", ""])
    if warnings:
        lines.extend(f"- `{item['code']}`: {item['detail']}" for item in warnings)
    else:
        lines.append("_No automatic warnings. This is not an approval._")
    lines.extend([
        "", "## Human Review", "",
        "- Question valid?:",
        "- Answer (APPROVE / EDIT / REJECT):",
        "- Required facts (APPROVE / EDIT):",
        "- Evidence (APPROVE / EDIT / UNRESOLVED):",
        "- Images (APPROVE / EDIT / N/A):",
        "- Chunk mapping:",
        "- Overall (APPROVE / EDITED_APPROVE / QUARANTINE / NEEDS_SECOND_REVIEW):",
        "- Human notes:", "",
    ])
    return "\n".join(lines)


def render_index(split: str, records: list[dict[str, Any]]) -> str:
    label = split.upper()
    lines = [
        f"# {label} Gold Review Index", "",
        "> All entries are machine-proposed and UNREVIEWED. This index contains no runtime model output or retrieval diagnostics.", "",
        "| ID | Language | Question | Candidate manuals | Evidence | Mapping | Warnings | Item |",
        "|---:|---|---|---|---|---|---:|---|",
    ]
    for record in sorted(records, key=lambda row: numeric_key(row["id"])):
        manuals = sorted({v.get("manual_title") for v in record["candidate_source_evidence"] if v.get("manual_title")})
        e_resolved = sum(v["resolution_status"] in RESOLVED_EVIDENCE_STATUSES for v in record["candidate_source_evidence"])
        question = record["question"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {record['id']} | {record['language']} | {question} | {', '.join(manuals) or 'unresolved'} | "
            f"{e_resolved}/{len(record['candidate_source_evidence'])} proposed spans | "
            f"{record['candidate_chunk_mapping']['mapping_status']} | {len(record['automatic_warnings'])} | "
            f"[open](items/{record['id']}.md) |"
        )
    return "\n".join(lines) + "\n"


def write_split(split: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    directory = OUTPUT_ROOT / split
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / "review_records.jsonl", records)
    prefix = split.upper()
    write_review_csv(directory / f"{prefix}_GOLD_REVIEW.csv", records)
    (directory / f"{prefix}_GOLD_REVIEW.md").write_text(render_index(split, records), encoding="utf-8")
    items = directory / "items"
    items.mkdir(parents=True, exist_ok=True)
    expected_names = {f"{record['id']}.md" for record in records}
    for stale in items.glob("*.md"):
        if stale.name not in expected_names:
            stale.unlink()
    for record in records:
        (items / f"{record['id']}.md").write_text(render_item(record), encoding="utf-8")
    summary = warning_summary(records)
    write_json(directory / f"{prefix}_AUTOMATIC_WARNINGS.json", summary)
    return summary


def stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    def evidence_count(row: dict[str, Any]) -> int:
        return sum(
            item["resolution_status"] in RESOLVED_EVIDENCE_STATUSES
            for item in row["candidate_source_evidence"]
        )

    has_evidence = [evidence_count(row) for row in records]
    applicable_images = [row for row in records if row["candidate_gold_images"]]
    return {
        "total": len(records),
        "candidate_answer_available": sum(bool(row["candidate_reference_answer"].strip()) for row in records),
        "source_evidence_resolved": sum(count > 0 for count in has_evidence),
        "source_evidence_fully_resolved": sum(
            count == len(row["candidate_source_evidence"])
            for count, row in zip(has_evidence, records)
        ),
        "source_evidence_partially_resolved": sum(
            0 < count < len(row["candidate_source_evidence"])
            for count, row in zip(has_evidence, records)
        ),
        "source_evidence_unresolved": sum(count == 0 for count in has_evidence),
        "candidate_facts_generated": sum(bool(row["candidate_required_facts"]) for row in records),
        "image_applicable": len(applicable_images),
        "image_resolved": sum(
            all(v["resolution_status"] == "PROPOSED_RESOLVED" for v in row["candidate_gold_images"])
            for row in applicable_images
        ),
        "image_not_applicable": len(records) - len(applicable_images),
        "chunk_mapping_resolved": sum(row["candidate_chunk_mapping"]["mapping_status"] == "PROPOSED_RESOLVED" for row in records),
        "chunk_mapping_unresolved": sum(row["candidate_chunk_mapping"]["mapping_status"] == "CHUNK_MAPPING_UNRESOLVED" for row in records),
        "records_with_warnings": sum(bool(row["automatic_warnings"]) for row in records),
        "warning_count": sum(len(row["automatic_warnings"]) for row in records),
        "human_reviewed": 0,
        "human_gold_status": "PENDING_HUMAN_VERIFICATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Replace generated proposed assets. Never use after humans begin editing them.")
    args = parser.parse_args()
    existing = [OUTPUT_ROOT / split / f"{split.upper()}_GOLD_REVIEW.csv" for split in SPLITS]
    if any(path.exists() for path in existing) and not args.force:
        raise SystemExit("review assets already exist; use --force only before human editing starts")

    ensure_candidate_ancestry()
    hashes = data_hashes()
    answers = {str(row["id"]): row for row in __import__("baseline_v1_common").load_answers()[0]}
    chunks = load_chunk_levels()
    all_records: dict[str, list[dict[str, Any]]] = {}
    for split in SPLITS:
        references = {str(row["id"]): row for row in load_jsonl(ROOT / f"evaluation/gold_v2/{split}.jsonl")}
        split_rows = {str(row["id"]): row for row in load_jsonl(ROOT / f"evaluation/splits/v1/{split}.jsonl")}
        if set(references) != set(split_rows):
            raise SystemExit(f"{split}: Reference V2 IDs do not exactly match frozen split")
        missing = sorted(set(references) - set(answers), key=numeric_key)
        if missing:
            raise SystemExit(f"{split}: missing Silver source answers: {missing}")
        all_records[split] = [
            build_record(split, references[qid], split_rows[qid], answers[qid], chunks, hashes)
            for qid in sorted(references, key=numeric_key)
        ]
    combined = all_records["dev"] + all_records["heldout"]
    add_duplicate_warnings(combined)
    leaked = sorted(PROHIBITED_REVIEW_KEYS & recursive_keys(combined))
    if leaked:
        raise SystemExit(f"prohibited runtime fields in review records: {leaked}")

    warning_summaries = {split: write_split(split, records) for split, records in all_records.items()}
    manifest = {
        "schema_version": "interx-human-gold-verification-infra-v1",
        "candidate_commit": CANDIDATE_COMMIT,
        "foundation_source_commit": CANDIDATE_COMMIT,
        "dataset_name": "InterX-350 Silver Benchmark",
        "human_verification_complete": False,
        "dev_human_gold_status": "PENDING_HUMAN_VERIFICATION",
        "heldout_human_gold_status": "PENDING_HUMAN_VERIFICATION",
        "formal_dev_run_executed": False,
        "formal_heldout_run_executed": False,
        "algorithm_optimization_performed": False,
        "system_output_in_review_assets": False,
        "policies": {
            "source": "original manual/source span before any chunk-derived fallback",
            "facts": "source-verbatim conservative machine proposals requiring human approval",
            "mapping": "manual identity and source-line overlap only",
            "heldout": "separate; do not expose runtime outputs or use future errors for development",
        },
        "hashes": hashes,
        "input_hashes": {split: source_inputs_hash(split) for split in SPLITS},
        "statistics": {split: stats(records) for split, records in all_records.items()},
        "review_record_hashes": {split: sha256_records(records) for split, records in all_records.items()},
        "warning_code_counts": {
            split: warning_summaries[split]["warning_code_counts"] for split in SPLITS
        },
        "prohibited_review_keys": sorted(PROHIBITED_REVIEW_KEYS),
    }
    write_json(OUTPUT_ROOT / "verification_manifest.json", manifest)
    schema_path = OUTPUT_ROOT / "schema/human_gold_review_v1.schema.json"
    manifest["schema_hash"] = sha256_file(schema_path)
    write_json(OUTPUT_ROOT / "verification_manifest.json", manifest)

    lines = [
        "# Gold Verification Automatic Warning Summary", "",
        "> Warnings are triage signals only. They never change candidate data or confer approval.", "",
    ]
    for split in SPLITS:
        summary = warning_summaries[split]
        lines.extend([
            f"## {split.upper()}", "",
            f"- Records: {summary['record_count']}",
            f"- Records with warnings: {summary['records_with_warnings']}",
            f"- Warning instances: {summary['warning_count']}", "",
            "| Warning | Count |", "|---|---:|",
        ])
        lines.extend(f"| `{code}` | {count} |" for code, count in summary["warning_code_counts"].items())
        lines.append("")
    (OUTPUT_ROOT / "GOLD_VERIFICATION_WARNING_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(manifest["statistics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
