"""Single-question human-readable audit for zh Hit@1 (read-only).

Selection: from the existing baseline50 run, pool = questions with
lang=zh AND gold coverage.chunk AND error is None, sorted by int(id);
random.seed(20260716); random.choice(pool). No model rerun, no file mutation
outside evaluation/audits/.

Prints, as structured JSON to stdout:
  - question / gold answer / raw evidence_refs from the label file
  - gold build trace for this question (channel, scores, thresholds, lines use)
  - full text + metadata of every gold chunk (from process artifacts)
  - top-5 retrieval hits saved by the baseline run (chunk_id, text, doc,
    dense/bm25/rerank/final scores)
  - manual hit@1/3/5 + MRR computation
  - the per-question entry computed by compute_metrics.py for cross-check
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "evaluation" / "results" / "baseline50"
GOLD = ROOT / "evaluation" / "gold" / "gold.jsonl"


def jload(path):
    return json.load(open(path, encoding="utf-8"))


def main():
    gold = {json.loads(l)["id"]: json.loads(l) for l in open(GOLD, encoding="utf-8")}
    raws = {}
    for l in open(RUN / "raw.jsonl", encoding="utf-8"):
        r = json.loads(l)
        raws[r["id"]] = r  # last record per id wins, same as compute_metrics

    pool = sorted(
        (qid for qid, r in raws.items()
         if r["lang"] == "zh" and not r.get("error")
         and gold[qid]["coverage"]["chunk"]),
        key=int,
    )
    random.seed(20260716)
    qid = random.choice(pool)

    g = gold[qid]
    r = raws[qid]

    # raw label file (original evidence_refs, untouched)
    label_path = next(ROOT.glob(f"agentic-rag/answers/*/per_question/{qid}.json"))
    label = jload(label_path)

    # full chunk texts for gold chunks and top5 hits
    need = {c["chunk_id"] for c in g["gold_chunks"]}
    hits = sorted(r["retrieval"]["small_hits"], key=lambda h: h["rank"])[:5]
    need |= {h["chunk_id"] for h in hits}
    chunk_info = {}
    for fp in (ROOT / "process/artifacts/manuals").glob("*/small_chunks.jsonl"):
        for line in open(fp, encoding="utf-8"):
            d = json.loads(line)
            if d["chunk_id"] in need:
                chunk_info[d["chunk_id"]] = {
                    "doc_name": d["doc_name"],
                    "content": d["content"],
                    "source_path": d.get("source_path"),
                    "source_span": d.get("source_span"),
                    "section_title": d.get("section_title"),
                    "header_path": d.get("header_path"),
                    "image_paths": d.get("image_paths"),
                }

    # manual metrics
    ranked = [h["chunk_id"] for h in sorted(r["retrieval"]["small_hits"], key=lambda h: h["rank"])]
    gold_ids = set(g["gold_chunk_ids"])
    first = next((i for i, cid in enumerate(ranked, 1) if cid in gold_ids), None)
    manual = {
        "top1_chunk": ranked[0],
        "top1_in_gold": ranked[0] in gold_ids,
        "hit@1": 1.0 if any(c in gold_ids for c in ranked[:1]) else 0.0,
        "hit@3": 1.0 if any(c in gold_ids for c in ranked[:3]) else 0.0,
        "hit@5": 1.0 if any(c in gold_ids for c in ranked[:5]) else 0.0,
        "first_gold_rank": first,
        "mrr": (1.0 / first) if first else 0.0,
        "gold_ranks_in_top20": [i for i, cid in enumerate(ranked, 1) if cid in gold_ids],
    }

    # program-computed entry
    metrics = jload(RUN / "metrics.json")
    prog = next(e for e in metrics["per_question"] if e["id"] == qid)

    out = {
        "selection": {"seed": 20260716, "pool_sorted_by_int_id": pool, "picked": qid},
        "question": g["question"],
        "gold_answer": g["gold_answer"],
        "label_file": str(label_path.relative_to(ROOT)),
        "evidence_refs_raw": label.get("evidence_refs"),
        "gold_build": {
            "gold_chunks": g["gold_chunks"],
            "unmapped_refs": g["unmapped_refs"],
            "thresholds": jload(ROOT / "evaluation/gold/gold_build_config.json")["thresholds"],
        },
        "gold_chunk_texts": {cid: chunk_info.get(cid) for cid in g["gold_chunk_ids"]},
        "top5": [{
            "rank": h["rank"], "chunk_id": h["chunk_id"], "doc_name": h["doc_name"],
            "final_score": h["score"], "scores_breakdown": h.get("scores"),
            "retrieval_source": h["retrieval_source"],
            "content": chunk_info.get(h["chunk_id"], {}).get("content", h.get("content")),
        } for h in hits],
        "manual_metrics": manual,
        "program_metrics_entry": {k: prog.get(k) for k in
                                  ("hit@1", "hit@3", "hit@5", "mrr", "first_rank",
                                   "recall@1", "recall@3", "recall@5")},
        "final_answer": r["qa_result"]["final_answer"],
        "router": r.get("router"),
        "wall_seconds": r.get("wall_seconds"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
