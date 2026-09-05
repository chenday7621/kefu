"""Shared, dependency-free helpers for the InterX Baseline V1 toolchain."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
AGENTIC = ROOT / "agentic-rag"
ARTIFACT_MANUALS = ROOT / "process" / "artifacts" / "manuals"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_records(records: Iterable[dict[str, Any]]) -> str:
    payload = "\n".join(canonical_json(row) for row in records) + "\n"
    return sha256_bytes(payload.encode("utf-8"))


def sha256_tree(root: Path) -> str:
    """Hash relative paths and file content without embedding machine-specific roots."""
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return sha256_records(entries)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    result = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return result


def normalize_question(text: str) -> str:
    """Normalize formatting-only differences without changing question semantics."""
    value = str(text or "").strip()
    value = value.replace("\\\"", '"').replace("\\M\\", '"M"')
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", value)


def load_questions() -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    duplicate_ids: list[str] = []
    seen: set[str] = set()
    for filename, language in (("ch-question.csv", "zh"), ("en-question.csv", "en")):
        with (AGENTIC / filename).open(encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                qid = str(raw.get("id") or "").strip()
                if qid in seen:
                    duplicate_ids.append(qid)
                seen.add(qid)
                rows.append({
                    "id": qid,
                    "question": normalize_question(raw.get("clean") or raw.get("raw") or ""),
                    "language": language,
                    "source_file": filename,
                })
    return rows, sorted(set(duplicate_ids), key=numeric_key)


def answer_paths() -> list[Path]:
    return sorted(AGENTIC.glob("answers/*/per_question/*.json"), key=lambda p: numeric_key(p.stem))


def load_answers() -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for path in answer_paths():
        value = json.loads(path.read_text(encoding="utf-8"))
        qid = str(value.get("id") or path.stem).strip()
        if qid in seen:
            duplicates.append(qid)
        seen.add(qid)
        value["id"] = qid
        value["_source_path"] = path.relative_to(ROOT).as_posix()
        rows.append(value)
    return rows, sorted(set(duplicates), key=numeric_key)


def load_legacy_gold() -> dict[str, dict[str, Any]]:
    path = ROOT / "evaluation" / "gold" / "gold.jsonl"
    return {str(row["id"]): row for row in load_jsonl(path)} if path.exists() else {}


def load_chunk_index() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(ARTIFACT_MANUALS.glob("*/small_chunks.jsonl")):
        for row in load_jsonl(path):
            result[str(row["chunk_id"])] = row
    return result


def numeric_key(value: str) -> tuple[int, str]:
    text = str(value)
    return (int(text), text) if text.isdigit() else (10**18, text)


def find_manual(source: str | None) -> Path | None:
    if not source:
        return None
    cleaned = str(source).strip().replace("\\", "/")
    cleaned = re.sub(r":\d+(?:[-,]\d+)*$", "", cleaned)
    candidate = ROOT / cleaned
    if candidate.exists() and candidate.is_file():
        return candidate
    name = Path(cleaned).name
    matches = list((AGENTIC / "ch-manual").glob(name)) + list((AGENTIC / "en-manual").glob(name))
    return matches[0] if len(matches) == 1 else None


def find_image(image_id: str) -> Path | None:
    roots = [
        AGENTIC / "ch-manual" / "插图",
        AGENTIC / "en-manual" / "插图",
        ROOT / "process" / "data" / "插图",
    ]
    for root in roots:
        for suffix in IMAGE_SUFFIXES:
            candidate = root / f"{image_id}{suffix}"
            if candidate.exists():
                return candidate
    return None


_RANGE_RE = re.compile(r"(?P<start>\d+)\s*(?:-|–|—|至|:)\s*(?P<end>\d+)")


def parse_line_ranges(value: Any) -> list[tuple[int, int]]:
    if value is None:
        return []
    if isinstance(value, int):
        return [(value, value)]
    text = str(value)
    ranges = [(int(m.group("start")), int(m.group("end"))) for m in _RANGE_RE.finditer(text)]
    if ranges:
        return ranges
    numbers = [int(v) for v in re.findall(r"\d+", text)]
    return [(number, number) for number in numbers]


def evidence_source(ref: Any) -> tuple[str | None, Any, str | None]:
    if isinstance(ref, dict):
        return ref.get("source") or ref.get("file"), ref.get("lines"), ref.get("text") or ref.get("summary") or ref.get("note")
    if isinstance(ref, str):
        match = re.match(r"^(.*?\.md)(?::(.+))?$", ref.strip())
        if match:
            return match.group(1), match.group(2), None
    return None, None, str(ref) if ref else None


def extract_source_text(source: str | None, lines: Any) -> tuple[str | None, str | None]:
    path = find_manual(source)
    ranges = parse_line_ranges(lines)
    if path is None or not ranges:
        return None, None
    content = path.read_text(encoding="utf-8").splitlines()
    selected: list[str] = []
    normalized_ranges: list[str] = []
    for start, end in ranges:
        lo, hi = sorted((start, end))
        if lo < 1 or lo > len(content):
            continue
        hi = min(hi, len(content))
        selected.extend(content[lo - 1:hi])
        normalized_ranges.append(f"{lo}-{hi}")
    text = "\n".join(selected).strip()
    location = f"{path.relative_to(ROOT).as_posix()}:{','.join(normalized_ranges)}" if normalized_ranges else None
    return (text or None), location


def infer_manual_key(answer: dict[str, Any], legacy: dict[str, Any] | None) -> str:
    docs = sorted(str(v) for v in (legacy or {}).get("gold_docs", []) if v)
    if docs:
        return "|".join(docs)
    guess = str(answer.get("manual_guess") or "").strip()
    if guess:
        return Path(guess).stem
    for ref in answer.get("evidence_refs") or []:
        source, _, _ = evidence_source(ref)
        path = find_manual(source)
        if path and path.name not in {"手册内容总览.md"}:
            return path.stem
    return f"unresolved::{answer['id']}"
