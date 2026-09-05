"""Regression check: with both phase-2 toggles off, retrieval must equal baseline50.

Compares per-question small-hit chunk_id sequences between the baseline50 run
and a fresh run of the same ids on the modified code. Also asserts that no
phase-2 artifacts (sub_questions / vlm_extraction / retrieval_calls) leaked
into the records while the toggles are off.
"""
import json
import sys

OLD = "evaluation/results/baseline50/raw.jsonl"
NEW = sys.argv[1] if len(sys.argv) > 1 else "/tmp/regress20.jsonl"

old = {json.loads(l)["id"]: json.loads(l) for l in open(OLD, encoding="utf-8")}
new = {json.loads(l)["id"]: json.loads(l) for l in open(NEW, encoding="utf-8")}

diff = 0
leaks = 0
for qid, n in sorted(new.items(), key=lambda x: int(x[0])):
    o = old[qid]
    oc = [h["chunk_id"] for h in (o.get("retrieval") or {}).get("small_hits", [])]
    nc = [h["chunk_id"] for h in (n.get("retrieval") or {}).get("small_hits", [])]
    if oc != nc:
        diff += 1
        common = len(set(oc) & set(nc))
        # find first divergence position
        pos = next((i for i, (a, b) in enumerate(zip(oc, nc)) if a != b), min(len(oc), len(nc)))
        print(f"DIFF id={qid} old_n={len(oc)} new_n={len(nc)} common={common} first_div_rank={pos + 1}")
    meta = (n.get("qa_result") or {}).get("recall_meta") or {}
    if meta.get("sub_questions"):
        leaks += 1
        print(f"LEAK sub_questions id={qid}: {meta['sub_questions']}")
    if meta.get("vlm_extraction"):
        leaks += 1
        print(f"LEAK vlm_extraction id={qid}")
    if "retrieval_calls" in n:
        leaks += 1
        print(f"LEAK retrieval_calls id={qid} n_calls={len(n['retrieval_calls'])}")

print(f"checked={len(new)} retrieval_diff={diff} phase2_leaks={leaks}")
print("PASS" if diff == 0 and leaks == 0 else "FAIL")
