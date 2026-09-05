"""Compare the decompose-on ablation run against the toggles-off regression run.

Reports: trigger rate + sub-question quality, strict hit@1/@5 on gold-covered
questions, wall-time delta. Read-only.
Usage: python3 evaluation/scripts/analyze_decompose_ablation.py [base.jsonl] [ablation.jsonl]
"""
import json
import statistics as st
import sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/regress20.jsonl"
ABL = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ablate_decompose20.jsonl"

base = {json.loads(l)["id"]: json.loads(l) for l in open(BASE, encoding="utf-8")}
abl = {json.loads(l)["id"]: json.loads(l) for l in open(ABL, encoding="utf-8")}
gold = {}
for line in open("evaluation/gold/gold.jsonl", encoding="utf-8"):
    g = json.loads(line)
    gold[g["id"]] = g

print("=== decompose triggers ===")
trig = 0
for qid, a in sorted(abl.items(), key=lambda x: int(x[0])):
    meta = (a.get("qa_result") or {}).get("recall_meta") or {}
    subs = meta.get("sub_questions") or []
    n_calls = len(a.get("retrieval_calls", [])) or 1
    if subs:
        trig += 1
        print(f"id={qid} ({n_calls} retrieval calls) Q: {a['question'][:50]}")
        for s in subs:
            print(f"   -> {s[:70]}")
print(f"trigger_rate: {trig}/20")


def hitk(rec, qid, k):
    g = gold.get(qid) or {}
    gc = {c["chunk_id"] for c in g.get("gold_chunks", [])}
    if not gc:
        return None
    hits = [h["chunk_id"] for h in (rec.get("retrieval") or {}).get("small_hits", [])][:k]
    return 1.0 if gc & set(hits) else 0.0


print("\n=== metrics (gold-covered questions only) ===")
for name, data in (("baseline-off ", base), ("decompose-on ", abl)):
    h1 = [x for x in (hitk(r, q, 1) for q, r in data.items()) if x is not None]
    h5 = [x for x in (hitk(r, q, 5) for q, r in data.items()) if x is not None]
    ws = [r["wall_seconds"] for r in data.values()]
    print(f"{name}: hit@1={st.mean(h1):.2f} hit@5={st.mean(h5):.2f} (n={len(h1)}) "
          f"wall mean={st.mean(ws):.1f}s p50={st.median(ws):.1f}s")

print("\n=== per-question hit deltas (only where changed) ===")
for qid in sorted(abl, key=int):
    for k in (1, 5):
        b, a = hitk(base[qid], qid, k), hitk(abl[qid], qid, k)
        if b is not None and a is not None and b != a:
            print(f"id={qid} hit@{k}: {b:.0f} -> {a:.0f}")
