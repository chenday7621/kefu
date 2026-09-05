"""Compute deterministic metrics from raw baseline results + gold mapping.

Every metric is computed ONLY over questions whose gold mapping supports it,
and each block reports its own eligible-question count (coverage) — chunk-level
numbers on 235/350 questions are meaningless without that context.

Blocks:
- retrieval  (questions with coverage.chunk): hit@1/3/5 (any gold chunk in
  top-k small hits), recall@1/3/5 (fraction of gold chunks in top-k), MRR
- image_chunks (coverage.image): hit@1/3/5 against chunks that contain a gold
  image — an independent, threshold-free relevance signal
- doc_routing (coverage.doc): hit@1/5 against gold_docs
- answers    (all ok): predicted vs gold image precision/recall/exact-match,
  answer length, <PIC> placeholder vs images-list consistency
- runtime    (all ok): mean/p50/p95 wall seconds; errors listed separately

Usage:
  python3 evaluation/scripts/compute_metrics.py \
      --raw evaluation/results/smoke5/raw.jsonl \
      --gold evaluation/gold/gold.jsonl \
      --out evaluation/results/smoke5/metrics.json \
      --errors-out evaluation/results/smoke5/error_samples.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KS = (1, 3, 5)


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    return vs[min(len(vs) - 1, max(0, round(p / 100 * (len(vs) - 1))))]


def rank_metrics(ranked_ids: list[str], gold: set[str], prefix: str, entry: dict):
    first = next((i for i, cid in enumerate(ranked_ids, 1) if cid in gold), None)
    entry[f"{prefix}first_rank"] = first
    entry[f"{prefix}mrr"] = (1.0 / first) if first else 0.0
    for k in KS:
        topk = ranked_ids[:k]
        entry[f"{prefix}hit@{k}"] = 1.0 if any(c in gold for c in topk) else 0.0
        entry[f"{prefix}recall@{k}"] = len(gold & set(topk)) / len(gold)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--errors-out", default=None)
    args = parser.parse_args()

    gold = {}
    with open(ROOT / args.gold, encoding="utf-8") as f:
        for line in f:
            g = json.loads(line)
            gold[g["id"]] = g

    # last record per id wins (--retry-errors appends a fresh record for the same id)
    by_id: dict[str, dict] = {}
    with open(ROOT / args.raw, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            by_id[str(rec["id"])] = rec
    raws = sorted(by_id.values(), key=lambda r: int(r["id"]))

    per_q, errors = [], []
    for r in raws:
        qid = r["id"]
        g = gold.get(qid)
        entry: dict = {"id": qid, "lang": r.get("lang")}
        if r.get("error"):
            errors.append(r)
            entry["error"] = r["error"]
            per_q.append(entry)
            continue

        qa = r["qa_result"]
        ret = r.get("retrieval") or {}
        small = sorted(ret.get("small_hits") or [], key=lambda h: h["rank"])
        ranked_ids = [h["chunk_id"] for h in small]
        entry["wall_seconds"] = r.get("wall_seconds")
        entry["routed_general"] = r.get("retrieval") is None
        entry["pred_images"] = qa["final_answer"].get("images", [])
        content = qa["final_answer"].get("content", "")
        entry["answer_len"] = len(content)
        entry["pic_placeholder_consistent"] = (
            1.0 if content.count("<PIC>") == len(entry["pred_images"]) else 0.0
        )

        if g:
            cov = g.get("coverage", {})
            if cov.get("chunk") and ranked_ids:
                rank_metrics(ranked_ids, set(g["gold_chunk_ids"]), "", entry)
            if cov.get("image") and g.get("gold_image_chunk_ids") and ranked_ids:
                rank_metrics(ranked_ids, set(g["gold_image_chunk_ids"]), "imgchunk_", entry)
            if cov.get("doc") and ranked_ids:
                gold_docs = set(g["gold_docs"])
                docs_ranked = []
                for h in small:
                    if h["doc_name"] not in docs_ranked:
                        docs_ranked.append(h["doc_name"])
                entry["doc_hit@1"] = 1.0 if docs_ranked[:1] and docs_ranked[0] in gold_docs else 0.0
                entry["doc_hit@5"] = 1.0 if any(dn in gold_docs for dn in docs_ranked[:5]) else 0.0
            gold_imgs = set(g.get("gold_images", []))
            pred_imgs = set(entry["pred_images"])
            if gold_imgs:
                entry["image_recall"] = len(gold_imgs & pred_imgs) / len(gold_imgs)
                entry["image_exact_match"] = 1.0 if gold_imgs == pred_imgs else 0.0
            if pred_imgs:
                entry["image_precision"] = len(gold_imgs & pred_imgs) / len(pred_imgs)
        per_q.append(entry)

    def agg(key: str, subset=None) -> dict | None:
        pool = subset if subset is not None else per_q
        vals = [e[key] for e in pool if e.get(key) is not None]
        if not vals:
            return None
        return {"mean": round(statistics.mean(vals), 4), "n": len(vals)}

    ok = [e for e in per_q if "error" not in e]
    times = [e["wall_seconds"] for e in ok if e.get("wall_seconds")]

    # router stats (records without a "router" field, e.g. older runs, are skipped)
    router_recs = [r.get("router") for r in raws if r.get("router")]
    router_times = [x["elapsed_s"] for x in router_recs]
    router_summary = {
        "calls": len(router_recs),
        "failed": sum(1 for x in router_recs if x["failed"]),
        "empty_return": sum(1 for x in router_recs if x.get("empty_return")),
        "failed_but_fallback_rag_ok": sum(1 for x in router_recs if x.get("fallback_to_rag")),
        "genuine_rag_route": sum(1 for x in router_recs if x["routed_rag"] and not x["failed"]),
        "routed_general": sum(1 for x in router_recs if not x["routed_rag"]),
        "elapsed_mean_s": round(statistics.mean(router_times), 2) if router_times else None,
        "elapsed_p50_s": round(pctl(router_times, 50), 2) if router_times else None,
        "elapsed_p95_s": round(pctl(router_times, 95), 2) if router_times else None,
    } if router_recs else None

    def block(keys, subset=None):
        return {k: agg(k, subset) for k in keys}

    ret_keys = [f"hit@{k}" for k in KS] + [f"recall@{k}" for k in KS] + ["mrr"]
    summary = {
        "counts": {
            "total_run": len(raws),
            "ok": len(ok),
            "errors": len(errors),
            "routed_general": sum(1 for e in ok if e.get("routed_general")),
            "chunk_eligible": sum(1 for e in ok if "mrr" in e),
            "imgchunk_eligible": sum(1 for e in ok if "imgchunk_mrr" in e),
            "doc_eligible": sum(1 for e in ok if "doc_hit@1" in e),
        },
        "retrieval_chunk_gold": block(ret_keys),
        "retrieval_image_chunks": block([f"imgchunk_{k}" for k in ret_keys]),
        "doc_routing": block(["doc_hit@1", "doc_hit@5"]),
        "answers": block(["image_recall", "image_precision", "image_exact_match",
                          "pic_placeholder_consistent", "answer_len"]),
        "per_lang": {
            lg: block(ret_keys, [e for e in ok if e.get("lang") == lg])
            for lg in ("zh", "en")
        },
        "runtime": {
            "mean_s": round(statistics.mean(times), 1) if times else None,
            "p50_s": round(pctl(times, 50), 1),
            "p95_s": round(pctl(times, 95), 1),
        },
        "router": router_summary,
    }

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "per_question": per_q}, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.errors_out and errors:
        ep = ROOT / args.errors_out
        ep.parent.mkdir(parents=True, exist_ok=True)
        with open(ep, "w", encoding="utf-8") as f:
            for e in errors:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"error samples -> {ep}")


if __name__ == "__main__":
    main()
