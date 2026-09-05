#!/usr/bin/env python3
"""Build evidence-bearing InterX Reference V2 records from governed Silver sources."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import (  # noqa: E402
    ROOT,
    evidence_source,
    extract_source_text,
    find_manual,
    load_answers,
    load_chunk_index,
    load_legacy_gold,
    numeric_key,
    sha256_file,
    sha256_records,
    write_json,
    write_jsonl,
)


def chunk_location(chunk: dict[str, Any]) -> str | None:
    doc_name = str(chunk.get("doc_name") or "")
    path = find_manual(f"{doc_name}.md")
    span = chunk.get("source_span") or {}
    if path and span.get("start_line"):
        return f"{path.relative_to(ROOT).as_posix()}:{span['start_line']}-{span.get('end_line', span['start_line'])}"
    return None


def source_evidence(ref: Any, *, language: str, verified_lines: bool) -> dict[str, Any]:
    source, lines, annotation = evidence_source(ref)
    explicit_text = ref.get("text") if isinstance(ref, dict) else None
    text = str(explicit_text).strip() if explicit_text else None
    location = None
    if text:
        path = find_manual(source)
        location = f"{path.relative_to(ROOT).as_posix()}:{lines}" if path and lines else None
        status = "source_resolved"
    elif language == "en" or verified_lines:
        text, location = extract_source_text(source, lines)
        status = "source_resolved" if text else ("annotation_only" if annotation else "unavailable")
    else:
        # Chinese line references were previously demonstrated to be unreliable.
        # Keep their annotation, but never present it to the Judge as source text.
        status = "annotation_only" if annotation else "unavailable"
    path = find_manual(source)
    return {
        "chunk_id": None,
        "text": text,
        "manual_id": path.stem if path else None,
        "section": None,
        "source_location": location,
        "resolution_status": status,
        "annotation": str(annotation).strip() if annotation else None,
    }


def main() -> int:
    governance = json.loads((ROOT / "evaluation" / "audits" / "dataset_governance_v1.json").read_text(encoding="utf-8"))
    governed = {str(row["id"]): row for row in governance["records"]}
    answers, _ = load_answers()
    amap = {str(row["id"]): row for row in answers}
    legacy = load_legacy_gold()
    chunks = load_chunk_index()
    split_for_id: dict[str, str] = {}
    split_root = ROOT / "evaluation" / "splits" / "v1"
    for split in ("train", "dev", "heldout", "quarantined"):
        path = split_root / f"{split}.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    split_for_id[str(json.loads(line)["id"])] = split

    records = []
    for qid in sorted(governed, key=numeric_key):
        meta, answer, old = governed[qid], amap[qid], legacy.get(qid, {})
        evidence = []
        for chunk_id in old.get("gold_chunk_ids") or []:
            chunk = chunks.get(str(chunk_id))
            if chunk is None:
                evidence.append({
                    "chunk_id": str(chunk_id), "text": None, "manual_id": None,
                    "section": None, "source_location": None,
                    "resolution_status": "unavailable", "annotation": "chunk ID absent from current corpus",
                })
                continue
            evidence.append({
                "chunk_id": str(chunk_id),
                "text": str(chunk.get("content") or chunk.get("text") or "").strip() or None,
                "manual_id": str(chunk.get("doc_id") or "") or None,
                "manual_name": str(chunk.get("doc_name") or "") or None,
                "section": str(chunk.get("section_title") or "") or None,
                "source_location": chunk_location(chunk),
                "resolution_status": "chunk_resolved",
                "annotation": None,
            })
        if not evidence:
            evidence = [
                source_evidence(ref, language=meta["language"], verified_lines=(qid == "65"))
                for ref in answer.get("evidence_refs") or []
            ]
        if not evidence:
            evidence = [{
                "chunk_id": None, "text": None, "manual_id": None, "section": None,
                "source_location": None, "resolution_status": "unavailable",
                "annotation": "no source evidence reference",
            }]
        gold_chunk_ids = sorted({str(v) for v in old.get("gold_chunk_ids") or []})
        gold_docs = sorted({str(v) for v in old.get("gold_docs") or []})
        gold_images = sorted({str(v) for v in old.get("gold_images") or []})
        gold_image_chunk_ids = sorted({str(v) for v in old.get("gold_image_chunk_ids") or []})
        record = {
            "id": qid,
            "question": meta["question"],
            "language": meta["language"],
            "quality_status": meta["quality_status"],
            "split": split_for_id.get(qid, "quarantined"),
            "reference_answer": str(answer.get("content") or "").strip() or None,
            "reference_answer_status": "agent_generated_silver" if meta["quality_status"] == "silver" else "source_binding_verified",
            "evidence": evidence,
            "gold_chunk_ids": gold_chunk_ids,
            "gold_docs": gold_docs,
            "gold_images": gold_images,
            "gold_image_chunk_ids": gold_image_chunk_ids,
            "coverage": {
                "chunk": bool(gold_chunk_ids), "document": bool(gold_docs), "image": bool(gold_images),
                "evidence_text": any(bool(item.get("text")) for item in evidence),
            },
            "source_provenance": {
                "dataset": "InterX-350 Silver Benchmark",
                "source_question_id": meta["source_question_id"],
                "source_answer_id": meta["source_answer_id"],
                "source_question_file": meta["source_question_file"],
                "source_answer_file": meta["source_answer_file"],
                "legacy_reference_schema": "evaluation/gold/gold.jsonl",
                "evidence_policy": "chunk text first; reliable source lines second; unresolved fields remain null",
                "audit_reason": meta.get("audit_reason", []),
            },
        }
        records.append(record)

    out = ROOT / "evaluation" / "gold_v2"
    write_jsonl(out / "references.jsonl", records)
    for split in ("train", "dev", "heldout", "quarantined"):
        write_jsonl(out / f"{split}.jsonl", [row for row in records if row["split"] == split])
    sample_ids = ["65"]
    for split in ("dev", "heldout"):
        for language in ("zh", "en"):
            selected = next(
                (row["id"] for row in records if row["split"] == split and row["language"] == language),
                None,
            )
            if selected and selected not in sample_ids:
                sample_ids.append(selected)
    write_jsonl(out / "sample.jsonl", [row for row in records if row["id"] in sample_ids])
    manifest = {
        "schema_version": "gold-reference-v2",
        "dataset_name": "InterX-350 Silver Benchmark",
        "record_count": len(records),
        "quality_status_counts": {
            status: sum(row["quality_status"] == status for row in records)
            for status in ("silver", "verified", "quarantined")
        },
        "coverage": {
            key: sum(bool(row["coverage"][key]) for row in records)
            for key in ("chunk", "document", "image", "evidence_text")
        },
        "dataset_hash": governance["dataset_hash"],
        "legacy_reference_hash": sha256_file(ROOT / "evaluation" / "gold" / "gold.jsonl"),
        "schema_hash": sha256_file(out / "schema.json"),
        "references_hash": sha256_records(records),
        "build_script": "evaluation/scripts/build_gold_v2.py",
        "sample_ids": sample_ids,
    }
    write_json(out / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
