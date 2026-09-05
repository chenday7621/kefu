#!/usr/bin/env python3
"""Audit all InterX-350 Silver source records and emit governance metadata."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import (  # noqa: E402
    ROOT,
    evidence_source,
    find_image,
    find_manual,
    infer_manual_key,
    load_answers,
    load_chunk_index,
    load_legacy_gold,
    load_questions,
    normalize_question,
    numeric_key,
    sha256_file,
    sha256_records,
    write_json,
)


def source_exists(source: str | None) -> bool | None:
    if not source:
        return None
    cleaned = re.sub(r":\d+(?:[-,]\d+)*$", "", source.strip().replace("\\", "/"))
    candidate = ROOT / cleaned
    if candidate.exists():
        return True
    if Path(cleaned).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        return find_image(Path(cleaned).stem) is not None
    return find_manual(cleaned) is not None


def main() -> int:
    questions, duplicate_question_ids = load_questions()
    answers, duplicate_answer_ids = load_answers()
    legacy = load_legacy_gold()
    chunks = load_chunk_index()
    qmap = {row["id"]: row for row in questions}
    amap = {row["id"]: row for row in answers}
    all_ids = sorted(set(qmap) | set(amap), key=numeric_key)
    records: list[dict[str, Any]] = []

    for qid in all_ids:
        question = qmap.get(qid)
        answer = amap.get(qid)
        gold = legacy.get(qid, {})
        errors: list[str] = []
        warnings: list[str] = []
        if question is None:
            errors.append("missing_question")
        if answer is None:
            errors.append("missing_answer")
        if answer is None or question is None:
            status = "quarantined"
            records.append({
                "id": qid, "quality_status": status, "audit_reason": errors,
                "source_question_id": qid if question else None,
                "source_answer_id": qid if answer else None,
                "language": question.get("language") if question else None,
            })
            continue

        source_language = "zh" if "/ch-answers/" in f"/{answer['_source_path']}" else "en"
        if source_language != question["language"]:
            errors.append("language_mismatch")
        aligned = normalize_question(answer.get("question", "")) == normalize_question(question["question"])
        if not aligned:
            errors.append("question_answer_text_mismatch")
        if not str(answer.get("content") or "").strip():
            errors.append("empty_reference_answer")

        evidence_checks = []
        for index, ref in enumerate(answer.get("evidence_refs") or []):
            source, lines, summary = evidence_source(ref)
            exists = source_exists(source)
            evidence_checks.append({
                "index": index, "source": source, "lines": lines,
                "source_exists": exists, "has_text_or_summary": bool(summary),
            })
            if source and exists is False:
                warnings.append(f"evidence_source_missing:{index}")
        if not evidence_checks:
            warnings.append("no_evidence_refs")

        images = [str(v) for v in answer.get("images") or []]
        missing_images = [image_id for image_id in images if find_image(image_id) is None]
        if missing_images:
            errors.append("missing_image_files")
        chunk_ids = [str(v) for v in gold.get("gold_chunk_ids") or []]
        missing_chunks = [chunk_id for chunk_id in chunk_ids if chunk_id not in chunks]
        if missing_chunks:
            errors.append("missing_chunk_references")

        manual_key = infer_manual_key(answer, gold)
        if manual_key.startswith("unresolved::"):
            warnings.append("manual_unresolved")
        if qid == "65":
            status = "verified"
            warnings.append("id65_source_binding_repaired_from_blower_manual")
        elif qid == "305":
            status = "silver"
            warnings.append("id305_format_normalized_semantics_unchanged")
        else:
            status = "quarantined" if errors else "silver"

        records.append({
            "id": qid,
            "question": question["question"],
            "quality_status": status,
            "audit_reason": sorted(set(errors + warnings)),
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
            "source_question_id": qid,
            "source_answer_id": str(answer["id"]),
            "source_question_file": question["source_file"],
            "source_answer_file": answer["_source_path"],
            "language": question["language"],
            "manual_id": manual_key if "|" not in manual_key else None,
            "manual_ids": manual_key.split("|") if not manual_key.startswith("unresolved::") else [],
            "question_type": None,
            "question_type_status": "unavailable_not_inferred",
            "has_chunk_gold": bool(gold.get("coverage", {}).get("chunk")),
            "has_doc_gold": bool(gold.get("coverage", {}).get("doc")),
            "has_image_gold": bool(gold.get("coverage", {}).get("image")),
            "question_answer_text_aligned": aligned,
            "reference_answer_present": bool(str(answer.get("content") or "").strip()),
            "evidence_reference_count": len(evidence_checks),
            "evidence_checks": evidence_checks,
            "image_reference_count": len(images),
            "missing_image_ids": missing_images,
            "chunk_reference_count": len(chunk_ids),
            "missing_chunk_ids": missing_chunks,
        })

    counts = Counter(row.get("quality_status") for row in records)
    error_counts = Counter(error for row in records for error in row.get("errors", []))
    warning_counts = Counter(warning.split(":", 1)[0] for row in records for warning in row.get("warnings", []))
    source_files = [
        ROOT / "agentic-rag" / "ch-question.csv",
        ROOT / "agentic-rag" / "en-question.csv",
        *[ROOT / row["_source_path"] for row in answers],
    ]
    report = {
        "schema_version": "dataset-governance-v1",
        "dataset_name": "InterX-350 Silver Benchmark",
        "dataset_hash": sha256_records([
            {"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in sorted(source_files)
        ]),
        "summary": {
            "question_count": len(questions),
            "answer_count": len(answers),
            "record_count": len(records),
            "duplicate_question_ids": duplicate_question_ids,
            "duplicate_answer_ids": duplicate_answer_ids,
            "missing_question_ids": sorted(set(amap) - set(qmap), key=numeric_key),
            "missing_answer_ids": sorted(set(qmap) - set(amap), key=numeric_key),
            "quality_status_counts": dict(sorted(counts.items())),
            "error_counts": dict(sorted(error_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
            "chunk_gold_count": sum(bool(row.get("has_chunk_gold")) for row in records),
            "doc_gold_count": sum(bool(row.get("has_doc_gold")) for row in records),
            "image_gold_count": sum(bool(row.get("has_image_gold")) for row in records),
        },
        "records": records,
    }
    out = ROOT / "evaluation" / "audits" / "dataset_governance_v1.json"
    write_json(out, report)

    md = [
        "# InterX-350 Silver Benchmark — Dataset Governance V1",
        "",
        "> This audit treats the 350 Agent-generated references as Silver data. Only explicitly audited records may be marked `verified`.",
        "",
        "## Summary", "",
        f"- Questions / answers / joined records: {len(questions)} / {len(answers)} / {len(records)}",
        f"- Quality states: `{dict(sorted(counts.items()))}`",
        f"- Coverage: chunk={report['summary']['chunk_gold_count']}, doc={report['summary']['doc_gold_count']}, image={report['summary']['image_gold_count']}",
        f"- Duplicate question IDs: `{duplicate_question_ids}`",
        f"- Duplicate answer IDs: `{duplicate_answer_ids}`",
        f"- Fatal audit findings: `{dict(sorted(error_counts.items()))}`",
        f"- Warnings: `{dict(sorted(warning_counts.items()))}`",
        f"- Canonical source dataset hash: `{report['dataset_hash']}`",
        "",
        "## Explicit repairs", "",
        "- **ID 65 — verified source-binding repair.** The prior drill answer was replaced at the per-question source layer with a blower-safety answer grounded only in `吹风机手册.md:54-68,75-111`. Derived aggregates were rebuilt.",
        "- **ID 305 — formatting normalization only.** The malformed `\\M\\` clean text was normalized to `\"M\"`; answer semantics were unchanged.",
        "",
        "## Interpretation", "",
        "`silver` means structurally auditable but not authoritative. `verified` applies only to the named audit decision, not to every factual detail in the entire dataset. `quarantined` records are excluded from formal splits and metrics.",
        "",
        "The JSON companion contains one record per ID, source existence checks, coverage flags, missing references, and provenance paths.",
    ]
    (out.with_suffix(".md")).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 1 if duplicate_question_ids or duplicate_answer_ids or report["summary"]["missing_question_ids"] or report["summary"]["missing_answer_ids"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
