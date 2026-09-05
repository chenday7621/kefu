"""Stratified 50-question sample for the Original Baseline validation run.

Strata are built from gold.jsonl along the dimensions the run must cover:
  - language (zh / en)
  - gold mapping channel present on the question (C1t / C1p / C2 / none)
  - chunk gold coverage (covered / not)
  - image evidence (has gold images / not)
Doc diversity is enforced inside each stratum: questions are sorted by
(doc, id) and picked at evenly spaced positions, so one manual cannot
dominate a stratum. Fully deterministic — no RNG.

Quota: proportional to stratum size (largest-remainder), language split fixed
to the population ratio (zh 163/350 -> 23, en 187/350 -> 27).

Usage: python3 evaluation/scripts/sample_stratified.py [--n 50]
Writes evaluation/results/baseline50/sample_ids.json (ids + per-stratum table).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evaluation" / "gold" / "gold.jsonl"
OUT = ROOT / "evaluation" / "results" / "baseline50" / "sample_ids.json"


def stratum_key(g: dict) -> tuple:
    channels = sorted({c["channel"] for c in g["gold_chunks"]}) or ["none"]
    return (
        g["lang"],
        "+".join(channels),
        "chunk" if g["coverage"]["chunk"] else "nochunk",
        "img" if g["coverage"]["image"] else "noimg",
    )


def spread_pick(items: list[dict], k: int) -> list[dict]:
    """Pick k items at evenly spaced positions after sorting by (doc, id)."""
    items = sorted(items, key=lambda g: ((g["gold_docs"] or ["~none"])[0], int(g["id"])))
    if k >= len(items):
        return items
    return [items[round(i * (len(items) - 1) / max(1, k - 1))] for i in range(k)] if k > 1 \
        else [items[len(items) // 2]]


def allocate(strata: dict, total: int) -> dict:
    """Largest-remainder proportional allocation, min 1 per non-empty stratum."""
    n_all = sum(len(v) for v in strata.values())
    raw = {k: len(v) * total / n_all for k, v in strata.items()}
    base = {k: max(1, int(r)) for k, r in raw.items()}
    # trim if the +min-1 floor overshot
    while sum(base.values()) > total:
        k = max((k for k in base if base[k] > 1),
                key=lambda k: base[k] - raw[k], default=None)
        if k is None:
            break
        base[k] -= 1
    rem = total - sum(base.values())
    for k in sorted(strata, key=lambda k: raw[k] - int(raw[k]), reverse=True)[:max(0, rem)]:
        base[k] += 1
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()

    gold = [json.loads(l) for l in open(GOLD, encoding="utf-8")]
    by_lang = defaultdict(list)
    for g in gold:
        by_lang[g["lang"]].append(g)

    lang_quota = {lg: round(args.n * len(qs) / len(gold)) for lg, qs in by_lang.items()}
    # fix rounding drift
    drift = args.n - sum(lang_quota.values())
    if drift:
        lang_quota[max(by_lang, key=lambda lg: len(by_lang[lg]))] += drift

    picked: list[dict] = []
    table = []
    for lg, quota in sorted(lang_quota.items()):
        strata = defaultdict(list)
        for g in by_lang[lg]:
            strata[stratum_key(g)].append(g)
        alloc = allocate(strata, quota)
        for key in sorted(strata):
            take = spread_pick(strata[key], alloc.get(key, 0))
            picked.extend(take)
            table.append({
                "stratum": "|".join(key),
                "population": len(strata[key]),
                "sampled": len(take),
                "ids": [g["id"] for g in take],
            })

    ids = sorted({g["id"] for g in picked}, key=int)
    docs = sorted({d for g in picked for d in g["gold_docs"]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"n": len(ids), "ids": ids, "distinct_docs": len(docs),
                   "strata": table}, f, ensure_ascii=False, indent=2)

    print(f"sampled {len(ids)} questions across {len(table)} strata, "
          f"{docs and len(docs)} distinct gold docs")
    for row in table:
        print(f"  {row['stratum']:<38} pop={row['population']:<4} take={row['sampled']}")
    print(f"ids -> {OUT}")
    print(",".join(ids))


if __name__ == "__main__":
    main()
