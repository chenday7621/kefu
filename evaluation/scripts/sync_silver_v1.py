#!/usr/bin/env python3
"""Rebuild answer aggregate files from per-question Silver source records."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_answers, numeric_key  # noqa: E402


def main() -> int:
    answers, duplicates = load_answers()
    if duplicates:
        raise SystemExit(f"duplicate answer IDs: {duplicates}")
    grouped = {"zh": [], "en": []}
    for row in answers:
        language = "zh" if "/ch-answers/" in f"/{row['_source_path']}" else "en"
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        grouped[language].append(clean)
    targets = {
        "zh": ROOT / "agentic-rag" / "answers" / "ch-answers",
        "en": ROOT / "agentic-rag" / "answers" / "en-answers",
    }
    for language, rows in grouped.items():
        rows.sort(key=lambda row: numeric_key(str(row["id"])))
        base = targets[language]
        jsonl_name = "ch-answers.jsonl" if language == "zh" else "answers.jsonl"
        csv_name = "ch-answers.csv" if language == "zh" else "answers.csv"
        with (base / jsonl_name).open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (base / csv_name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "ret"])
            writer.writeheader()
            for row in rows:
                writer.writerow({"id": row["id"], "ret": row.get("ret", "")})
    print(f"synced zh={len(grouped['zh'])} en={len(grouped['en'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

