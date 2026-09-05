#!/usr/bin/env python3
"""Export a deterministic, stratified, version-blinded human Judge sample."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_jsonl, write_json, write_jsonl  # noqa: E402


SEED = 20260904


def stable_order(qid: str) -> str:
    return hashlib.sha256(f"{SEED}:{qid}".encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="evaluation/results/baseline350/raw.jsonl")
    parser.add_argument("--references", default="evaluation/gold_v2/references.jsonl")
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--out-dir", default="evaluation/judge/calibration/sample_v1")
    args = parser.parse_args()
    if args.size < 2:
        raise SystemExit("--size must be at least 2")

    refs = {str(row["id"]): row for row in load_jsonl(ROOT / args.references)}
    raw = {}
    for row in load_jsonl(ROOT / args.raw):
        raw[str(row["id"])] = row
    buckets = defaultdict(list)
    for qid, ref in refs.items():
        # Calibration never consumes the formal Heldout split.
        if ref.get("split") not in {"train", "dev"} or ref.get("quality_status") == "quarantined":
            continue
        result = raw.get(qid)
        if not result or result.get("error") or not result.get("qa_result"):
            continue
        gold = set(ref.get("gold_chunk_ids") or [])
        hits = (result.get("retrieval") or {}).get("small_hits") or []
        retrieval = "unavailable" if not gold else ("hit" if hits and hits[0].get("chunk_id") in gold else "miss")
        manual = (ref.get("gold_docs") or ["unresolved"])[0]
        key = (ref["language"], retrieval, bool(gold), bool(ref.get("gold_images")))
        buckets[key].append((stable_order(qid), qid, manual))
    for values in buckets.values():
        values.sort()

    selected = []
    seen_manuals = set()
    keys = sorted(buckets, key=str)
    while len(selected) < min(args.size, sum(map(len, buckets.values()))):
        progressed = False
        for key in keys:
            values = buckets[key]
            if not values:
                continue
            preferred = next((i for i, value in enumerate(values) if value[2] not in seen_manuals), 0)
            _, qid, manual = values.pop(preferred)
            selected.append(qid)
            seen_manuals.add(manual)
            progressed = True
            if len(selected) >= args.size:
                break
        if not progressed:
            break

    out_dir = ROOT / args.out_dir
    json_rows, csv_rows = [], []
    for index, qid in enumerate(selected, 1):
        ref, result = refs[qid], raw[qid]
        subset = "calibration" if index % 2 else "validation"
        blind_id = f"HJ-{index:03d}"
        evidence = "\n\n---\n\n".join(
            str(item["text"]) for item in ref.get("evidence") or [] if item.get("text")
        )
        common = {
            "blind_item_id": blind_id,
            "subset": subset,
            "question": ref["question"],
            "reference_answer": ref.get("reference_answer") or "",
            "source_evidence": evidence,
            "system_answer": result["qa_result"]["final_answer"].get("content", ""),
            "human_answer_correctness": "",
            "human_completeness": "",
            "human_faithfulness": "",
            "human_binary_accept": "",
            "human_notes": "",
        }
        csv_rows.append(common)
        json_rows.append({**common, "source_id": qid})
    out_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(csv_rows[0]) if csv_rows else []
    with (out_dir / "human_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    write_jsonl(out_dir / "human_review.jsonl", json_rows)
    rubric = """# Human Judge Rubric V1

Reviewers do not receive a system version name. Score every dimension from 1 to 5.

- **Answer correctness:** factual agreement with source evidence and reference.
- **Completeness:** coverage of material answer elements supported by evidence.
- **Faithfulness:** no factual assertion beyond the supplied source evidence.
- **Binary accept:** `1` only if correctness and faithfulness are both at least 4;
  otherwise `0`.

If source evidence is empty, faithfulness must be scored `1` and the limitation
recorded in notes. Do not use outside knowledge. The calibration subset may be
used to revise the Judge rubric/prompt. The validation subset is evaluated only
after that revision is frozen. Neither subset is the model-quality Heldout split.
"""
    (out_dir / "RUBRIC.md").write_text(rubric, encoding="utf-8")
    write_json(out_dir / "sample_manifest.json", {
        "seed": SEED, "requested_size": args.size, "actual_size": len(selected),
        "calibration_count": sum(i % 2 == 1 for i in range(1, len(selected) + 1)),
        "validation_count": sum(i % 2 == 0 for i in range(1, len(selected) + 1)),
        "allowed_source_splits": ["train", "dev"], "heldout_used": False,
        "selection": "round-robin strata with manual-diversity preference",
    })
    print(f"human_sample={len(selected)} out={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
