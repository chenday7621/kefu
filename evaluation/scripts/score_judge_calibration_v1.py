#!/usr/bin/env python3
"""Compare completed human ratings with per-item Judge V1 results."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_jsonl, write_json  # noqa: E402


DIMS = ("answer_correctness", "completeness", "faithfulness")


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    result = [0.0] * len(values)
    ordered = sorted(range(len(values)), key=values.__getitem__)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for index in ordered[start:end]:
            result[index] = rank
        start = end
    return result


def score_rows(human: dict[str, dict], judge: dict[str, dict], *, subset: str | None) -> dict:
    selected = {
        blind_id: row for blind_id, row in human.items()
        if subset is None or row.get("subset") == subset
    }
    report = {"dimensions": {}, "binary": {}}
    for dim in DIMS:
        hs, js = [], []
        for blind_id, hrow in selected.items():
            jrow = judge.get(blind_id)
            raw_h = hrow.get(f"human_{dim}")
            score = ((jrow or {}).get("parsed_scores") or {}).get(dim, {}).get("score")
            if raw_h not in {None, ""} and isinstance(score, (int, float)):
                hs.append(float(raw_h)); js.append(float(score))
        report["dimensions"][dim] = {
            "n": len(hs), "pearson": pearson(hs, js),
            "spearman": pearson(ranks(hs), ranks(js)) if hs else None,
            "mae": sum(abs(a - b) for a, b in zip(hs, js)) / len(hs) if hs else None,
        }
    paired_binary = []
    for blind_id, hrow in selected.items():
        jrow = judge.get(blind_id)
        if hrow.get("human_binary_accept") in {"0", "1"} and jrow and jrow.get("parsed_scores"):
            scores = jrow["parsed_scores"]
            predicted = int(scores["answer_correctness"]["score"] >= 4 and scores["faithfulness"]["score"] >= 4)
            paired_binary.append((int(hrow["human_binary_accept"]), predicted))
    if paired_binary:
        tp = sum(a == b == 1 for a, b in paired_binary); fp = sum(a == 0 and b == 1 for a, b in paired_binary)
        fn = sum(a == 1 and b == 0 for a, b in paired_binary)
        accuracy = sum(a == b for a, b in paired_binary) / len(paired_binary)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        report["binary"] = {
            "n": len(paired_binary), "agreement": accuracy, "accuracy": accuracy,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    else:
        report["binary"] = {"n": 0, "agreement": None, "accuracy": None, "f1": None}
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human", required=True)
    parser.add_argument("--mapping", help="human_review.jsonl containing blind_item_id/source_id")
    parser.add_argument("--judge", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with (ROOT / args.human).open(encoding="utf-8-sig", newline="") as handle:
        human = {row["blind_item_id"]: row for row in csv.DictReader(handle)}
    source_to_blind = {}
    mapping_path = ROOT / args.mapping if args.mapping else (ROOT / args.human).with_suffix(".jsonl")
    if mapping_path.exists():
        source_to_blind = {str(row["source_id"]): str(row["blind_item_id"]) for row in load_jsonl(mapping_path)}
    judge = {}
    for row in load_jsonl(ROOT / args.judge):
        key = str(row.get("blind_item_id") or source_to_blind.get(str(row.get("id"))) or row.get("id"))
        judge[key] = row
    report = {
        "status": "UNVALIDATED_JUDGE_METRIC",
        "overall": score_rows(human, judge, subset=None),
        "subsets": {
            "calibration": score_rows(human, judge, subset="calibration"),
            "validation": score_rows(human, judge, subset="validation"),
        },
    }
    write_json(ROOT / args.out, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
