#!/usr/bin/env python3
"""Create the frozen, manual-grouped, stratified Baseline V1 split."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, numeric_key, sha256_records, write_json, write_jsonl  # noqa: E402


SEED = 20260904
RATIOS = {"train": 0.70, "dev": 0.15, "heldout": 0.15}
FEATURES = ("count", "zh", "en", "chunk", "doc", "image")


def vector(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "count": len(rows),
        "zh": sum(row["language"] == "zh" for row in rows),
        "en": sum(row["language"] == "en" for row in rows),
        "chunk": sum(bool(row["has_chunk_gold"]) for row in rows),
        "doc": sum(bool(row["has_doc_gold"]) for row in rows),
        "image": sum(bool(row["has_image_gold"]) for row in rows),
    }


def objective(counts: dict[str, dict[str, int]], totals: dict[str, int]) -> float:
    score = 0.0
    for split, ratio in RATIOS.items():
        for feature in FEATURES:
            target = totals[feature] * ratio
            scale = max(1.0, target)
            weight = 3.0 if feature == "count" else 1.0
            score += weight * ((counts[split][feature] - target) / scale) ** 2
    return score


def assign(groups: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    totals = vector([row for rows in groups.values() for row in rows])
    names = sorted(groups)
    best_score = float("inf")
    best: dict[str, str] | None = None
    rng = random.Random(SEED)
    group_vectors = {name: vector(groups[name]) for name in names}
    for _ in range(6000):
        order = names[:]
        rng.shuffle(order)
        order.sort(key=lambda name: len(groups[name]), reverse=True)
        counts = {split: {feature: 0 for feature in FEATURES} for split in RATIOS}
        current: dict[str, str] = {}
        for name in order:
            choices = []
            for split in RATIOS:
                trial = {s: dict(values) for s, values in counts.items()}
                for feature, value in group_vectors[name].items():
                    trial[split][feature] += value
                choices.append((objective(trial, totals), split, trial))
            _, selected, counts = min(choices, key=lambda item: (item[0], item[1]))
            current[name] = selected
        score = objective(counts, totals)
        if score < best_score:
            best_score, best = score, current
    assert best is not None
    return best


def main() -> int:
    governance_path = ROOT / "evaluation" / "audits" / "dataset_governance_v1.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    active = [row for row in governance["records"] if row["quality_status"] != "quarantined"]
    quarantined = [row for row in governance["records"] if row["quality_status"] == "quarantined"]
    # Multi-manual questions connect their manuals into one leakage group. A
    # plain joined string is insufficient: {A|B} must also co-locate with every
    # {A} and {B} record.
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for row in active:
        manual_ids = list(row.get("manual_ids") or [])
        for manual_id in manual_ids:
            find(manual_id)
        for manual_id in manual_ids[1:]:
            union(manual_ids[0], manual_id)

    components: dict[str, set[str]] = defaultdict(set)
    for manual_id in parent:
        components[find(manual_id)].add(manual_id)
    component_key = {
        manual_id: "|".join(sorted(components[find(manual_id)]))
        for manual_id in parent
    }

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in active:
        manual_ids = list(row.get("manual_ids") or [])
        key = component_key[manual_ids[0]] if manual_ids else f"unresolved::{row['id']}"
        groups[key].append(row)
    assignment = assign(groups)
    split_rows = {split: [] for split in RATIOS}
    for group, rows in groups.items():
        split_rows[assignment[group]].extend(rows)
    for rows in split_rows.values():
        rows.sort(key=lambda row: numeric_key(row["id"]))
    quarantined.sort(key=lambda row: numeric_key(row["id"]))

    out = ROOT / "evaluation" / "splits" / "v1"
    for split, rows in split_rows.items():
        write_jsonl(out / f"{split}.jsonl", rows)
    write_jsonl(out / "quarantined.jsonl", quarantined)

    group_sets = {
        split: sorted(group for group, assigned in assignment.items() if assigned == split)
        for split in RATIOS
    }
    manual_sets = {
        split: sorted({manual for group in group_sets[split] for manual in group.split("|")})
        for split in RATIOS
    }
    overlap = {
        "train_dev": sorted(set(manual_sets["train"]) & set(manual_sets["dev"])),
        "train_heldout": sorted(set(manual_sets["train"]) & set(manual_sets["heldout"])),
        "dev_heldout": sorted(set(manual_sets["dev"]) & set(manual_sets["heldout"])),
    }
    manifest = {
        "schema_version": "split-manifest-v1",
        "dataset_name": "InterX-350 Silver Benchmark",
        "dataset_hash": governance["dataset_hash"],
        "seed": SEED,
        "ratios": RATIOS,
        "strategy": "manual-grouped deterministic stratification over language and chunk/doc/image coverage",
        "grouping_policy": "All records sharing the resolved manual group remain in one split.",
        "question_type": "not used; governance marks it unavailable rather than inferring labels",
        "counts": {split: vector(rows) for split, rows in split_rows.items()},
        "quarantined_count": len(quarantined),
        "manual_groups": manual_sets,
        "connected_manual_groups": group_sets,
        "manual_group_overlap": overlap,
        "id_hashes": {
            split: sha256_records([{"id": row["id"]} for row in rows])
            for split, rows in {**split_rows, "quarantined": quarantined}.items()
        },
    }
    manifest["split_hash"] = sha256_records([
        {"split": split, "ids": [row["id"] for row in rows]}
        for split, rows in {**split_rows, "quarantined": quarantined}.items()
    ])
    write_json(out / "split_manifest.json", manifest)
    readme = """# InterX Baseline V1 frozen splits

Dataset: **InterX-350 Silver Benchmark**. These files are generated by
`evaluation/scripts/make_splits_v1.py` with seed `20260904`.

The split is grouped by connected resolved manuals before stratification. A
multi-manual record joins all of its manuals into one connected component, so a
manual and its logically related questions cannot cross Train, Dev, and Heldout.
This is intentionally stricter than row-wise random splitting.

## Contract

- **Train** may be used for QA-derived KG construction, training, and data development.
- **Dev** may be used for experiments, parameter tuning, and bad-case analysis.
- **Heldout** must not participate in KG construction, prompt tuning,
  hyperparameter selection, or error-driven design. Run it only for a frozen
  candidate baseline or final candidate.
- **Quarantined** records are excluded from formal metrics.

The split must never be regenerated to improve scores. Re-running the same script
must reproduce the ID hashes in `split_manifest.json`; any intentional V2 split
requires a new directory and an explicit migration record.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    if any(overlap.values()):
        raise SystemExit(f"manual-group leakage detected: {overlap}")
    print(json.dumps({"counts": manifest["counts"], "split_hash": manifest["split_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
