"""Dump all facts needed for the full 12-question zh Hit@1 audit (read-only).

Pool: baseline50 questions with lang=zh AND gold coverage.chunk AND no error
(the same 12 as the single audit). For each question, emits: question, gold
answer head, gold chunks with channel/score, unmapped refs, program metrics,
and top-5 hits with doc/content (top1 full text) — everything the human
reviewer needs to judge semantic correctness. No mutation anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "evaluation" / "results" / "baseline50"


def main():
    gold = {json.loads(l)["id"]: json.loads(l)
            for l in open(ROOT / "evaluation/gold/gold.jsonl", encoding="utf-8")}
    raws = {}
    for l in open(RUN / "raw.jsonl", encoding="utf-8"):
        r = json.loads(l)
        raws[r["id"]] = r
    metrics = json.load(open(RUN / "metrics.json", encoding="utf-8"))
    prog = {e["id"]: e for e in metrics["per_question"]}

    pool = sorted((qid for qid, r in raws.items()
                   if r["lang"] == "zh" and not r.get("error")
                   and gold[qid]["coverage"]["chunk"]), key=int)

    # chunk text lookup for all needed ids
    need = set()
    for qid in pool:
        need |= set(gold[qid]["gold_chunk_ids"])
        hits = sorted(raws[qid]["retrieval"]["small_hits"], key=lambda h: h["rank"])[:5]
        need |= {h["chunk_id"] for h in hits}
    text = {}
    for fp in (ROOT / "process/artifacts/manuals").glob("*/small_chunks.jsonl"):
        for line in open(fp, encoding="utf-8"):
            d = json.loads(line)
            if d["chunk_id"] in need:
                text[d["chunk_id"]] = d["content"]

    out = []
    for qid in pool:
        g, r, p = gold[qid], raws[qid], prog[qid]
        hits = sorted(r["retrieval"]["small_hits"], key=lambda h: h["rank"])
        top5 = []
        for h in hits[:5]:
            c = text.get(h["chunk_id"], h.get("content") or "")
            top5.append({
                "rank": h["rank"], "chunk_id": h["chunk_id"], "doc": h["doc_name"],
                "score": round(h["score"], 4),
                "in_gold": h["chunk_id"] in set(g["gold_chunk_ids"]),
                "content_len": len(c),
                "content": c if h["rank"] == 1 else c[:220],
            })
        out.append({
            "id": qid,
            "question": g["question"],
            "gold_answer_head": g["gold_answer"][:200],
            "gold_docs": g["gold_docs"],
            "gold_chunks": g["gold_chunks"],
            "gold_chunk_texts": {cid: text.get(cid, "")[:300] for cid in g["gold_chunk_ids"]},
            "unmapped_refs": g["unmapped_refs"],
            "program": {k: p.get(k) for k in ("hit@1", "hit@5", "first_rank", "mrr")},
            "top5": top5,
        })
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
