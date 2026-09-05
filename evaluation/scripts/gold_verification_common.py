"""Shared primitives for Human Gold Verification infrastructure.

The functions in this module only prepare machine-proposed review material.
They never promote Silver data to verified or gold status.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from baseline_v1_common import (
    ROOT,
    find_image,
    find_manual,
    load_answers,
    load_jsonl,
    numeric_key,
    parse_line_ranges,
    sha256_records,
)


SCHEMA_VERSION = "human-gold-verification-review-v1"
CANDIDATE_COMMIT = "ecc33679d0fc993b60cea0abb8566633875b431f"
SPLITS = ("dev", "heldout")
OVERALL_DECISIONS = {
    "APPROVE",
    "EDITED_APPROVE",
    "QUARANTINE",
    "NEEDS_SECOND_REVIEW",
}
PROHIBITED_REVIEW_KEYS = {
    "system_answer",
    "retrieval_rank",
    "retrieval_score",
    "baseline_correctness",
    "baseline_hit",
}
RESOLVED_EVIDENCE_STATUSES = {"PROPOSED_SOURCE_SPAN_RESOLVED"}

CSV_FIELDS = [
    "schema_version",
    "id",
    "split",
    "language",
    "question",
    "candidate_manuals_json",
    "candidate_sections_json",
    "candidate_reference_answer",
    "candidate_required_facts_json",
    "candidate_optional_facts_json",
    "candidate_forbidden_claims_json",
    "candidate_source_evidence_json",
    "candidate_gold_images_json",
    "candidate_chunk_mapping_json",
    "candidate_resolution_status",
    "automatic_warnings_json",
    "source_provenance_json",
    "human_review_status",
    "human_question_valid",
    "human_reference_answer_status",
    "human_reference_answer_final",
    "human_required_facts_status",
    "human_required_facts_final_json",
    "human_source_evidence_status",
    "human_source_evidence_final_json",
    "human_source_evidence_unresolved_reason",
    "human_image_status",
    "human_image_final_json",
    "human_chunk_mapping_status",
    "human_chunk_mapping_final_json",
    "human_overall_decision",
    "human_quarantine_reason",
    "human_reviewer_notes",
    "human_reviewer_id",
    "human_reviewed_at",
]


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def char_ngrams(value: Any, n: int = 3) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    if len(text) < n:
        return {text}
    return {text[index:index + n] for index in range(len(text) - n + 1)}


def lexical_support(candidate: str, source: str, language: str) -> float:
    """Return conservative source-to-candidate lexical coverage."""
    if language == "en":
        tokens = set(re.findall(r"[a-z0-9]+", source.lower()))
        candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate.lower()))
        return len(tokens & candidate_tokens) / max(1, len(tokens))
    source_ngrams = char_ngrams(source)
    return len(source_ngrams & char_ngrams(candidate)) / max(1, len(source_ngrams))


def heading_path(lines: list[str], line_number: int) -> list[str]:
    stack: list[tuple[int, str]] = []
    for raw in lines[:max(0, line_number)]:
        match = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", raw)
        if not match:
            continue
        level = len(match.group(1))
        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        stack = [(old_level, old_title) for old_level, old_title in stack if old_level < level]
        stack.append((level, title))
    return [title for _, title in stack]


def _source_span(
    path: Path | None,
    ranges: list[tuple[int, int]],
) -> tuple[str | None, list[dict[str, int]], list[str], list[str]]:
    """Extract exact source lines and report invalid spans without guessing."""
    if path is None:
        return None, [], [], ["source_manual_missing"]
    if not ranges:
        return None, [], [], ["source_lines_missing"]
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    normalized: list[dict[str, int]] = []
    issues: list[str] = []
    sections: list[str] = []
    for start, end in ranges:
        lo, hi = sorted((int(start), int(end)))
        if lo < 1 or hi > len(lines):
            issues.append(f"source_lines_invalid:{lo}-{hi}:manual_lines={len(lines)}")
            continue
        block = "\n".join(lines[lo - 1:hi]).strip()
        if not block:
            issues.append(f"evidence_text_empty:{lo}-{hi}")
            continue
        blocks.append(block)
        normalized.append({"start": lo, "end": hi})
        section = " > ".join(heading_path(lines, lo))
        if section and section not in sections:
            sections.append(section)
    return ("\n\n".join(blocks) or None), normalized, sections, issues


def _location(path: Path | None, spans: list[dict[str, int]]) -> str | None:
    if path is None or not spans:
        return None
    suffix = ",".join(f"{span['start']}-{span['end']}" for span in spans)
    return f"{path.relative_to(ROOT).as_posix()}:{suffix}"


def review_evidence_source(ref: Any) -> tuple[str | None, Any, str | None]:
    """Read every source-reference spelling present in the Silver answer files."""
    if isinstance(ref, dict):
        source = ref.get("source") or ref.get("file") or ref.get("manual")
        lines = ref.get("lines")
        if source and lines is None:
            match = re.match(r"^(.*?\.md):(.+)$", str(source).strip())
            if match:
                source, lines = match.group(1), match.group(2)
        annotation = (
            ref.get("text") or ref.get("summary") or ref.get("note")
            or ref.get("notes") or ref.get("evidence")
        )
        return source, lines, annotation
    if isinstance(ref, str):
        match = re.match(r"^(.*?\.md)(?::(.+))?$", ref.strip())
        if match:
            return match.group(1), match.group(2), None
    return None, None, str(ref) if ref else None


def resolve_candidate_source_evidence(
    answer: dict[str, Any],
    reference: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    """Resolve proposed source spans from Silver refs, never from system output."""
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str | None, tuple[tuple[int, int], ...]]] = set()
    for index, raw_ref in enumerate(answer.get("evidence_refs") or [], 1):
        source, raw_lines, annotation = review_evidence_source(raw_ref)
        path = find_manual(source)
        ranges = parse_line_ranges(raw_lines)
        text, spans, section_strings, issues = _source_span(path, ranges)
        key = (
            path.relative_to(ROOT).as_posix() if path else str(source or ""),
            tuple((span["start"], span["end"]) for span in spans),
        )
        if key in seen and spans:
            continue
        seen.add(key)
        support = lexical_support(str(answer.get("content") or ""), text or "", language) if text else 0.0
        status = "PROPOSED_SOURCE_SPAN_RESOLVED" if text and not issues else "UNRESOLVED"
        warnings = list(issues)
        if status in RESOLVED_EVIDENCE_STATUSES and support < (0.18 if language == "zh" else 0.22):
            warnings.append("source_span_low_lexical_support")
        evidence.append({
            "evidence_id": f"E{index}",
            "manual_id": path.stem if path else None,
            "manual_title": path.stem if path else None,
            "section_path": section_strings[0].split(" > ") if section_strings else [],
            "source_location": _location(path, spans),
            "source_lines": spans,
            "evidence_text": text,
            "resolution_status": status,
            "resolution_method": "source_reference_line_span" if status in RESOLVED_EVIDENCE_STATUSES else "unresolved_source_reference",
            "unresolved_reason": "; ".join(issues) if issues else None,
            "candidate_annotation": str(annotation).strip() if annotation else None,
            "candidate_answer_lexical_support": round(support, 4),
            "automatic_warnings": sorted(set(warnings)),
            "machine_proposed": True,
        })

    # Only when no original manual span can be extracted, fall back to a current
    # Candidate chunk's source span. This is explicitly lower priority and still
    # remains proposed for human confirmation.
    if not any(item["resolution_status"] in RESOLVED_EVIDENCE_STATUSES for item in evidence):
        for old in reference.get("evidence") or []:
            location = old.get("source_location")
            if not location or not old.get("chunk_id"):
                continue
            match = re.match(r"^(.*\.md):(.+)$", str(location))
            if not match:
                continue
            path = ROOT / match.group(1)
            ranges = parse_line_ranges(match.group(2))
            text, spans, section_strings, issues = _source_span(path if path.is_file() else None, ranges)
            if not text or issues:
                continue
            key = (path.relative_to(ROOT).as_posix(), tuple((s["start"], s["end"]) for s in spans))
            if key in seen:
                continue
            seen.add(key)
            evidence.append({
                "evidence_id": f"E{len(evidence) + 1}",
                "manual_id": path.stem,
                "manual_title": path.stem,
                "section_path": section_strings[0].split(" > ") if section_strings else [],
                "source_location": _location(path, spans),
                "source_lines": spans,
                "evidence_text": text,
                "resolution_status": "PROPOSED_SOURCE_SPAN_RESOLVED",
                "resolution_method": "candidate_chunk_source_span_fallback",
                "unresolved_reason": None,
                "candidate_annotation": "Fallback from an existing Candidate chunk mapping; human confirmation required.",
                "candidate_answer_lexical_support": round(
                    lexical_support(str(answer.get("content") or ""), text, language), 4
                ),
                "automatic_warnings": ["source_span_from_chunk_mapping_fallback"],
                "machine_proposed": True,
            })

    if not evidence:
        evidence.append({
            "evidence_id": "E1",
            "manual_id": None,
            "manual_title": None,
            "section_path": [],
            "source_location": None,
            "source_lines": [],
            "evidence_text": None,
            "resolution_status": "UNRESOLVED",
            "resolution_method": "no_source_reference",
            "unresolved_reason": "No evidence reference or resolvable chunk source span was available.",
            "candidate_annotation": None,
            "candidate_answer_lexical_support": 0.0,
            "automatic_warnings": ["missing_evidence"],
            "machine_proposed": True,
        })
    return evidence


def _evidence_statements(text: str, language: str) -> list[str]:
    statements: list[str] = []
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    for raw_line in cleaned.splitlines():
        line = re.sub(r"^\s*(?:#{1,6}|[-*+] |\d+[.)]\s*)", "", raw_line).strip()
        if not line:
            continue
        parts = re.split(r"(?<=[。！？；.!?;])\s*", line)
        for part in parts:
            part = part.strip()
            if language == "zh" and len(normalize_text(part)) < 8:
                continue
            if language == "en" and len(re.findall(r"[A-Za-z0-9]+", part)) < 4:
                continue
            statements.append(part)
    return statements


def propose_required_facts(
    candidate_answer: str,
    evidence: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    """Propose only source-verbatim facts with answer overlap."""
    candidates: list[tuple[float, str, str]] = []
    for item in evidence:
        if item.get("resolution_status") not in RESOLVED_EVIDENCE_STATUSES:
            continue
        for statement in _evidence_statements(str(item.get("evidence_text") or ""), language):
            score = lexical_support(candidate_answer, statement, language)
            threshold = 0.42 if language == "zh" else 0.50
            if score >= threshold:
                candidates.append((score, statement, str(item["evidence_id"])))
    facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, statement, evidence_id in sorted(candidates, key=lambda row: (-row[0], row[1])):
        key = normalize_text(statement)
        if not key or key in seen:
            continue
        seen.add(key)
        facts.append({
            "fact_id": f"F{len(facts) + 1}",
            "text": statement,
            "source_evidence_ids": [evidence_id],
            "support_method": "source_verbatim_with_candidate_answer_lexical_overlap",
            "support_score": round(score, 4),
            "machine_proposed": True,
        })
        if len(facts) >= 12:
            break
    return facts


def load_chunk_levels(corpus_dir: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    corpus = corpus_dir or ROOT / "process" / "artifacts" / "manuals"
    result: dict[str, list[dict[str, Any]]] = {"small": [], "mid": [], "big": []}
    for level in result:
        for path in sorted(corpus.glob(f"*/{level}_chunks.jsonl")):
            result[level].extend(load_jsonl(path))
    return result


def remap_source_record(
    record: dict[str, Any],
    chunks: dict[str, list[dict[str, Any]]],
    *,
    corpus_hash: str,
) -> dict[str, Any]:
    """Map source spans by deterministic line overlap; never use similarity."""
    source_items = record.get("source_gold") or record.get("candidate_source_evidence") or []
    groups: list[dict[str, Any]] = []
    unions: dict[str, set[str]] = {"small": set(), "mid": set(), "big": set()}
    resolved_group_count = 0
    for item in source_items:
        if item.get("resolution_status") not in RESOLVED_EVIDENCE_STATUSES and not item.get("human_verified"):
            continue
        manual = normalize_text(item.get("manual_title") or item.get("manual_id"))
        spans = [(int(s["start"]), int(s["end"])) for s in item.get("source_lines") or []]
        acceptable: dict[str, list[str]] = {}
        for level, rows in chunks.items():
            ids = []
            for chunk in rows:
                if normalize_text(chunk.get("doc_name")) != manual:
                    continue
                chunk_span = chunk.get("source_span") or {}
                if not chunk_span.get("start_line") or not chunk_span.get("end_line"):
                    continue
                c_start, c_end = int(chunk_span["start_line"]), int(chunk_span["end_line"])
                if any(max(c_start, start) <= min(c_end, end) for start, end in spans):
                    ids.append(str(chunk["chunk_id"]))
            acceptable[level] = sorted(set(ids))
            unions[level].update(acceptable[level])
        group_status = "PROPOSED_RESOLVED" if acceptable["small"] else "CHUNK_MAPPING_UNRESOLVED"
        resolved_group_count += group_status == "PROPOSED_RESOLVED"
        groups.append({
            "group_id": str(item.get("evidence_id") or f"G{len(groups) + 1}"),
            "source_location": item.get("source_location"),
            "source_lines": item.get("source_lines") or [],
            "acceptable_chunks": acceptable,
            "mapping_status": group_status,
        })
    if not groups or resolved_group_count == 0:
        status = "CHUNK_MAPPING_UNRESOLVED"
    elif resolved_group_count == len(groups):
        status = "PROPOSED_RESOLVED"
    else:
        status = "PROPOSED_PARTIAL"
    return {
        "acceptable_small_chunk_ids": sorted(unions["small"]),
        "acceptable_mid_chunk_ids": sorted(unions["mid"]),
        "acceptable_big_chunk_ids": sorted(unions["big"]),
        "evidence_groups": groups,
        "mapping_status": status,
        "mapping_method": "manual_identity_and_source_line_overlap",
        "chunk_corpus_hash": corpus_hash,
        "machine_proposed": True,
    }


def proposed_images(reference: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for image_id in sorted(set(str(v) for v in reference.get("gold_images") or [])):
        path = find_image(image_id)
        result.append({
            "image_id": image_id,
            "source_path": path.relative_to(ROOT).as_posix() if path else None,
            "resolution_status": "PROPOSED_RESOLVED" if path else "UNRESOLVED",
            "machine_proposed": True,
        })
    return result


def empty_human_review() -> dict[str, Any]:
    return {
        "review_status": "UNREVIEWED",
        "question_valid": None,
        "reference_answer_status": None,
        "reference_answer_final": None,
        "required_facts_status": None,
        "required_facts_final": None,
        "source_evidence_status": None,
        "source_evidence_final": None,
        "source_evidence_unresolved_reason": None,
        "image_status": None,
        "image_final": None,
        "chunk_mapping_status": None,
        "chunk_mapping_final": None,
        "overall_decision": None,
        "quarantine_reason": None,
        "reviewer_notes": None,
        "reviewer_id": None,
        "reviewed_at": None,
    }


def recursive_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys.update(recursive_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(recursive_keys(nested))
    return keys


def record_warnings(
    record: dict[str, Any],
    *,
    expected_manuals: set[str],
    answer_source_id: str,
    question_source_id: str,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []

    def add(code: str, detail: str) -> None:
        if not any(item["code"] == code and item["detail"] == detail for item in warnings):
            warnings.append({"code": code, "detail": detail})

    if answer_source_id != question_source_id or answer_source_id != str(record["id"]):
        add("QUESTION_ANSWER_ID_MISMATCH", f"question={question_source_id}, answer={answer_source_id}")
        add("ANSWER_EVIDENCE_CONFLICT", "Question and answer source IDs differ; human review required.")
    if not str(record.get("candidate_reference_answer") or "").strip():
        add("CANDIDATE_ANSWER_MISSING", "Silver candidate answer is empty.")
    evidence = record["candidate_source_evidence"]
    resolved = [item for item in evidence if item["resolution_status"] in RESOLVED_EVIDENCE_STATUSES]
    if not evidence:
        add("MISSING_EVIDENCE", "No candidate evidence entries exist.")
    if not resolved:
        add("SOURCE_EVIDENCE_UNRESOLVED", "No original-manual source span was resolved.")
    for item in evidence:
        if item["resolution_status"] in RESOLVED_EVIDENCE_STATUSES and not item.get("evidence_text"):
            add("EVIDENCE_TEXT_EMPTY", item["evidence_id"])
        for issue in item.get("automatic_warnings") or []:
            code = {
                "source_manual_missing": "SOURCE_MANUAL_MISSING",
                "source_lines_missing": "SOURCE_LINES_MISSING",
                "source_span_low_lexical_support": "SOURCE_SPAN_AMBIGUOUS",
                "source_span_from_chunk_mapping_fallback": "SOURCE_SPAN_FROM_CHUNK_FALLBACK",
                "missing_evidence": "MISSING_EVIDENCE",
            }.get(issue.split(":", 1)[0], "SOURCE_LINES_INVALID")
            add(code, f"{item['evidence_id']}: {issue}")
    evidence_manuals = {
        normalize_text(item.get("manual_title"))
        for item in resolved if item.get("manual_title")
    }
    normalized_expected = {normalize_text(v) for v in expected_manuals if v}
    if normalized_expected and evidence_manuals and not (normalized_expected & evidence_manuals):
        add("MANUAL_MISMATCH", f"expected={sorted(expected_manuals)}, evidence={sorted(evidence_manuals)}")
        add("ANSWER_EVIDENCE_CONFLICT", "Candidate evidence manuals do not match the proposed document labels.")
    if len(evidence_manuals) > 1:
        add("MULTIPLE_MANUALS", f"manuals={sorted(evidence_manuals)}")
    images = record["candidate_gold_images"]
    for image in images:
        if image["resolution_status"] == "UNRESOLVED":
            add("IMAGE_UNRESOLVED", image["image_id"])
    if record["candidate_chunk_mapping"]["mapping_status"] == "CHUNK_MAPPING_UNRESOLVED":
        add("CHUNK_MAPPING_UNRESOLVED", "No deterministic source-line overlap mapping was found.")
    elif record["candidate_chunk_mapping"]["mapping_status"] == "PROPOSED_PARTIAL":
        add("CHUNK_MAPPING_PARTIAL", "At least one source evidence group has no small-chunk overlap.")
    if not record["candidate_required_facts"]:
        add("CANDIDATE_REQUIRED_FACTS_NEEDS_HUMAN_REVIEW", "No source-verbatim fact met the conservative answer-overlap threshold.")
        if resolved:
            add("CANDIDATE_ANSWER_NO_SOURCE_SUPPORT", "No candidate-answer claim could be linked conservatively to the extracted source text.")
    question = str(record["question"])
    if record["language"] == "zh" and not re.search(r"[\u3400-\u9fff]", question):
        add("LANGUAGE_MISMATCH", "Expected zh but question has no CJK character.")
    if record["language"] == "en" and len(re.findall(r"[\u3400-\u9fff]", question)) > 2:
        add("LANGUAGE_MISMATCH", "Expected en but question contains multiple CJK characters.")
    return sorted(warnings, key=lambda item: (item["code"], item["detail"]))


def add_duplicate_warnings(records: list[dict[str, Any]]) -> None:
    question_groups: dict[str, list[str]] = defaultdict(list)
    answer_groups: dict[str, list[str]] = defaultdict(list)
    for record in records:
        question_groups[normalize_text(record["question"])].append(str(record["id"]))
        answer_groups[normalize_text(record.get("candidate_reference_answer"))].append(str(record["id"]))
    for record in records:
        qids = question_groups[normalize_text(record["question"])]
        aids = answer_groups[normalize_text(record.get("candidate_reference_answer"))]
        if len(qids) > 1:
            record["automatic_warnings"].append({"code": "DUPLICATE_QUESTION", "detail": f"ids={sorted(qids, key=numeric_key)}"})
        if normalize_text(record.get("candidate_reference_answer")) and len(aids) > 1:
            record["automatic_warnings"].append({"code": "SUSPICIOUSLY_IDENTICAL_ANSWER", "detail": f"ids={sorted(aids, key=numeric_key)}"})
        record["automatic_warnings"] = sorted(record["automatic_warnings"], key=lambda x: (x["code"], x["detail"]))


def record_to_csv(record: dict[str, Any]) -> dict[str, Any]:
    human = record["human_review"]
    sections = sorted({" > ".join(v.get("section_path") or []) for v in record["candidate_source_evidence"] if v.get("section_path")})
    manuals = sorted({v.get("manual_title") for v in record["candidate_source_evidence"] if v.get("manual_title")})
    as_json = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    def nullable(value: Any) -> Any:
        return "" if value is None else value

    def nullable_json(value: Any) -> str:
        return "" if value is None else as_json(value)

    return {
        "schema_version": record["schema_version"],
        "id": record["id"],
        "split": record["split"],
        "language": record["language"],
        "question": record["question"],
        "candidate_manuals_json": as_json(manuals),
        "candidate_sections_json": as_json(sections),
        "candidate_reference_answer": record["candidate_reference_answer"],
        "candidate_required_facts_json": as_json(record["candidate_required_facts"]),
        "candidate_optional_facts_json": as_json(record["candidate_optional_facts"]),
        "candidate_forbidden_claims_json": as_json(record["candidate_forbidden_claims"]),
        "candidate_source_evidence_json": as_json(record["candidate_source_evidence"]),
        "candidate_gold_images_json": as_json(record["candidate_gold_images"]),
        "candidate_chunk_mapping_json": as_json(record["candidate_chunk_mapping"]),
        "candidate_resolution_status": record["candidate_resolution_status"],
        "automatic_warnings_json": as_json(record["automatic_warnings"]),
        "source_provenance_json": as_json(record.get("source_provenance") or {}),
        "human_review_status": human["review_status"],
        "human_question_valid": nullable(human.get("question_valid")),
        "human_reference_answer_status": nullable(human.get("reference_answer_status")),
        "human_reference_answer_final": nullable(human.get("reference_answer_final")),
        "human_required_facts_status": nullable(human.get("required_facts_status")),
        "human_required_facts_final_json": nullable_json(human.get("required_facts_final")),
        "human_source_evidence_status": nullable(human.get("source_evidence_status")),
        "human_source_evidence_final_json": nullable_json(human.get("source_evidence_final")),
        "human_source_evidence_unresolved_reason": nullable(human.get("source_evidence_unresolved_reason")),
        "human_image_status": nullable(human.get("image_status")),
        "human_image_final_json": nullable_json(human.get("image_final")),
        "human_chunk_mapping_status": nullable(human.get("chunk_mapping_status")),
        "human_chunk_mapping_final_json": nullable_json(human.get("chunk_mapping_final")),
        "human_overall_decision": nullable(human.get("overall_decision")),
        "human_quarantine_reason": nullable(human.get("quarantine_reason")),
        "human_reviewer_notes": nullable(human.get("reviewer_notes")),
        "human_reviewer_id": nullable(human.get("reviewer_id")),
        "human_reviewed_at": nullable(human.get("reviewed_at")),
    }


def write_review_csv(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(record_to_csv(record))


def _json_cell(row: dict[str, str], name: str, default: Any) -> Any:
    raw = str(row.get(name) or "").strip()
    return json.loads(raw) if raw else default


def _nullable_bool(value: Any) -> bool | None | Any:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return value


def csv_to_record(row: dict[str, str], source_record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = dict(source_record or {})
    record.update({
        "schema_version": row.get("schema_version") or SCHEMA_VERSION,
        "id": str(row["id"]),
        "split": row["split"],
        "language": row["language"],
        "question": row["question"],
        "candidate_reference_answer": row.get("candidate_reference_answer") or None,
        "candidate_required_facts": _json_cell(row, "candidate_required_facts_json", []),
        "candidate_optional_facts": _json_cell(row, "candidate_optional_facts_json", []),
        "candidate_forbidden_claims": _json_cell(row, "candidate_forbidden_claims_json", []),
        "candidate_source_evidence": _json_cell(row, "candidate_source_evidence_json", []),
        "candidate_gold_images": _json_cell(row, "candidate_gold_images_json", []),
        "candidate_chunk_mapping": _json_cell(row, "candidate_chunk_mapping_json", {}),
        "candidate_resolution_status": row.get("candidate_resolution_status"),
        "automatic_warnings": _json_cell(row, "automatic_warnings_json", []),
        "source_provenance": _json_cell(row, "source_provenance_json", {}),
    })
    record["human_review"] = {
        "review_status": row.get("human_review_status") or "UNREVIEWED",
        "question_valid": _nullable_bool(row.get("human_question_valid")),
        "reference_answer_status": row.get("human_reference_answer_status") or None,
        "reference_answer_final": row.get("human_reference_answer_final") or None,
        "required_facts_status": row.get("human_required_facts_status") or None,
        "required_facts_final": _json_cell(row, "human_required_facts_final_json", None),
        "source_evidence_status": row.get("human_source_evidence_status") or None,
        "source_evidence_final": _json_cell(row, "human_source_evidence_final_json", None),
        "source_evidence_unresolved_reason": row.get("human_source_evidence_unresolved_reason") or None,
        "image_status": row.get("human_image_status") or None,
        "image_final": _json_cell(row, "human_image_final_json", None),
        "chunk_mapping_status": row.get("human_chunk_mapping_status") or None,
        "chunk_mapping_final": _json_cell(row, "human_chunk_mapping_final_json", None),
        "overall_decision": row.get("human_overall_decision") or None,
        "quarantine_reason": row.get("human_quarantine_reason") or None,
        "reviewer_notes": row.get("human_reviewer_notes") or None,
        "reviewer_id": row.get("human_reviewer_id") or None,
        "reviewed_at": row.get("human_reviewed_at") or None,
    }
    return record


def load_review_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl(path)
    if path.suffix.lower() != ".csv":
        raise ValueError(f"unsupported review input: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [csv_to_record(row) for row in csv.DictReader(handle)]


def warning_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["code"] for record in records for item in record["automatic_warnings"])
    return {
        "record_count": len(records),
        "records_with_warnings": sum(bool(record["automatic_warnings"]) for record in records),
        "warning_count": sum(counts.values()),
        "warning_code_counts": dict(sorted(counts.items())),
        "records": [
            {"id": record["id"], "warnings": record["automatic_warnings"]}
            for record in records if record["automatic_warnings"]
        ],
    }


def data_hashes() -> dict[str, str]:
    environment = json.loads(
        (ROOT / "evaluation/baselines/baseline_v1_environment_manifest.json").read_text(encoding="utf-8")
    )
    return {
        "dataset": environment["hashes"]["dataset"],
        "split": environment["hashes"]["split"],
        "source_corpus": environment["hashes"]["corpus"],
        "reference_v2": environment["hashes"]["gold_v2"],
    }


def source_inputs_hash(split: str) -> str:
    records = load_jsonl(ROOT / f"evaluation/gold_v2/{split}.jsonl")
    return sha256_records(records)
