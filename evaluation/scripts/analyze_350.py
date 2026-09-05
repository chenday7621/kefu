"""Post-run deep-dive for baseline350. Read-only.

Prints: the failed question detail, zh miss structure (first_rank distribution,
per-manual hotspots), router failure split by language, and a concurrency
sanity check (reused-sequential 50 vs concurrent 300 on the same config).
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RDIR = ROOT / "evaluation" / "results" / "baseline350"


def main():
    m = json.load(open(RDIR / "metrics.json", encoding="utf-8"))
    pq = m["per_question"]
    raws = {}
    with open(RDIR / "raw.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            raws[r["id"]] = r  # keep last record per id

    print("=== 1. errors ===")
    for e in [e for e in pq if "error" in e]:
        r = raws[e["id"]]
        print(f"q{e['id']} [{r['lang']}] {r['question'][:50]}")
        print(f"  error: {(r.get('error') or '')[:200]}")
        print(f"  router: {r.get('router')}")

    zh = [e for e in pq if e["lang"] == "zh" and e.get("hit@1") is not None and "error" not in e]
    en = [e for e in pq if e["lang"] == "en" and e.get("hit@1") is not None and "error" not in e]

    print("\n=== 2. zh miss structure ===")
    zh_m1 = [e for e in zh if e["hit@1"] == 0]
    zh_m5 = [e for e in zh if e["hit@5"] == 0]
    print(f"zh chunk-eligible={len(zh)}  hit@1=0: {len(zh_m1)}  hit@5=0: {len(zh_m5)}")
    fr = [e.get("first_rank") for e in zh_m1]
    dist = collections.Counter(
        "rank2-3" if (x and x <= 3) else "rank4-5" if (x and x <= 5)
        else "rank6-20" if x else ">20/none" for x in fr)
    print(f"zh hit@1-miss first_rank dist: {dict(dist)}")
    mc = collections.Counter(d for e in zh_m5 for d in (e.get("gold_docs") or [])[:1])
    print(f"zh hit@5=0 by manual: {mc.most_common(10)}")

    print("\n=== 3. router failure by language ===")
    rl = collections.Counter()
    tot = collections.Counter()
    for r in raws.values():
        ro = r.get("router") or {}
        tot[r["lang"]] += 1
        if ro.get("failed"):
            rl[r["lang"]] += 1
    for lg in ("zh", "en"):
        print(f"  {lg}: {rl[lg]}/{tot[lg]} failed ({rl[lg]/max(1,tot[lg]):.0%})")

    print("\n=== 4. concurrency sanity (same config, reused-seq vs concurrent) ===")
    def wk(r):
        return r.get("workers") or 1
    avg = lambda xs: round(sum(x["hit@1"] for x in xs) / len(xs), 3) if xs else None
    for lg, arr in (("zh", zh), ("en", en)):
        seq = [e for e in arr if wk(raws[e["id"]]) == 1]
        con = [e for e in arr if wk(raws[e["id"]]) > 1]
        print(f"  {lg} hit@1  seq(n={len(seq)}): {avg(seq)}   concurrent(n={len(con)}): {avg(con)}")
    ws = collections.Counter(wk(r) for r in raws.values())
    print(f"  workers field distribution: {dict(ws)}")

    print("\n=== 5. slowest 5 ===")
    slow = sorted((e for e in pq if e.get("wall_seconds")), key=lambda e: -e["wall_seconds"])[:5]
    for e in slow:
        print(f"  q{e['id']} {e['wall_seconds']}s")


if __name__ == "__main__":
    main()
