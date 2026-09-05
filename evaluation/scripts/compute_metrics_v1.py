#!/usr/bin/env python3
"""Compute deterministic Baseline V1 metrics, trace coverage, and outliers."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_jsonl, write_json  # noqa: E402


KS = (1, 3, 5)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(p / 100 * (len(ordered) - 1))))]


def stats(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4) if values else None,
        "p50": round(percentile(values, 50), 4) if values else None,
        "p95": round(percentile(values, 95), 4) if values else None,
    }


def rank_metrics(ranked: list[str], gold: set[str], row: dict[str, Any], prefix: str = "") -> None:
    first = next((index for index, item in enumerate(ranked, 1) if item in gold), None)
    row[f"{prefix}mrr"] = 1 / first if first else 0.0
    row[f"{prefix}first_rank"] = first
    for k in KS:
        top = set(ranked[:k])
        row[f"{prefix}hit@{k}"] = float(bool(top & gold))
        row[f"{prefix}recall@{k}"] = len(top & gold) / len(gold)


def mean_metric(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    return {"mean": round(statistics.mean(values), 4), "n": len(values)} if values else {"mean": None, "n": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--references", default="evaluation/gold_v2/references.jsonl")
    parser.add_argument("--split-file", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--outlier-seconds", type=float, default=300.0)
    args = parser.parse_args()
    references = {str(row["id"]): row for row in load_jsonl(ROOT / args.references)}
    expected = {str(row["id"]) for row in load_jsonl(ROOT / args.split_file)}
    latest = {}
    for row in load_jsonl(ROOT / args.raw):
        latest[str(row["id"])] = row
    unexpected = sorted(set(latest) - expected)
    missing = sorted(expected - set(latest))
    rows, errors = [], []
    for qid in sorted(expected & set(latest), key=int):
        raw, ref = latest[qid], references[qid]
        entry: dict[str, Any] = {"id": qid, "language": ref["language"]}
        if raw.get("error") or not raw.get("qa_result"):
            entry["error"] = raw.get("error") or "missing_qa_result"
            errors.append(entry)
            rows.append(entry)
            continue
        qa, retrieval = raw["qa_result"], raw.get("retrieval") or {}
        hits = sorted(retrieval.get("small_hits") or [], key=lambda item: item["rank"])
        ranked = [str(item["chunk_id"]) for item in hits]
        if ref["coverage"]["chunk"] and ranked:
            rank_metrics(ranked, set(ref["gold_chunk_ids"]), entry)
        image_chunks = set(ref.get("gold_image_chunk_ids") or [])
        if image_chunks and ranked:
            rank_metrics(ranked, image_chunks, entry, "imgchunk_")
        if ref["coverage"]["document"] and ranked:
            docs = []
            for hit in hits:
                if hit["doc_name"] not in docs:
                    docs.append(hit["doc_name"])
            gold_docs = set(ref["gold_docs"])
            entry["doc_hit@1"] = float(bool(set(docs[:1]) & gold_docs))
            entry["doc_hit@5"] = float(bool(set(docs[:5]) & gold_docs))
        answer = qa["final_answer"]
        predicted_images, gold_images = set(answer.get("images") or []), set(ref["gold_images"])
        if gold_images:
            entry["image_recall"] = len(predicted_images & gold_images) / len(gold_images)
            entry["image_exact_match"] = float(predicted_images == gold_images)
        if predicted_images:
            entry["image_precision"] = len(predicted_images & gold_images) / len(predicted_images)
        entry["pic_placeholder_consistent"] = float(answer.get("content", "").count("<PIC>") == len(answer.get("images") or []))
        entry["wall_seconds"] = raw.get("wall_seconds")
        entry["trace"] = qa.get("trace") or raw.get("trace")
        rows.append(entry)

    ok = [row for row in rows if "error" not in row]
    metric_keys = [f"hit@{k}" for k in KS] + [f"recall@{k}" for k in KS] + ["mrr"]
    traces = [row["trace"] for row in ok if isinstance(row.get("trace"), dict) and row["trace"].get("trace_id")]
    stage_names = sorted({name for trace in traces for name in (trace.get("stage_timings_ms") or {})})
    stage_stats = {
        stage: stats([float(trace["stage_timings_ms"][stage]) for trace in traces if isinstance(trace.get("stage_timings_ms", {}).get(stage), (int, float))])
        for stage in stage_names
    }
    times = [float(row["wall_seconds"]) for row in ok if isinstance(row.get("wall_seconds"), (int, float))]
    outliers = [row for row in ok if isinstance(row.get("wall_seconds"), (int, float)) and row["wall_seconds"] > args.outlier_seconds]
    fallback_counts = Counter(value for trace in traces for value in trace.get("fallbacks") or [])
    llm_calls = [int(trace.get("calls", {}).get("llm", 0)) for trace in traces]
    embedding_calls = [int(trace.get("calls", {}).get("embedding", 0)) for trace in traces]
    rerank_calls = [int(trace.get("calls", {}).get("rerank", 0)) for trace in traces]
    total_tokens = [trace.get("tokens", {}).get("total") for trace in traces]
    total_tokens = [int(value) for value in total_tokens if isinstance(value, int)]
    summary = {
        "metric_contract": {
            "dataset": "InterX-350 Silver Benchmark",
            "answer_reference_authority": "silver_not_authoritative",
            "judge_status": "UNVALIDATED_JUDGE_METRIC",
        },
        "completion": {
            "expected": len(expected), "observed": len(expected & set(latest)),
            "ok": len(ok), "errors": len(errors), "missing_ids": missing,
            "unexpected_ids": unexpected, "complete": not missing and not unexpected and not errors,
        },
        "retrieval_chunk_gold": {key: mean_metric(ok, key) for key in metric_keys},
        "retrieval_image_chunks": {f"imgchunk_{key}": mean_metric(ok, f"imgchunk_{key}") for key in metric_keys},
        "document": {key: mean_metric(ok, key) for key in ("doc_hit@1", "doc_hit@5")},
        "images": {key: mean_metric(ok, key) for key in ("image_recall", "image_precision", "image_exact_match", "pic_placeholder_consistent")},
        "per_language": {
            language: {key: mean_metric([row for row in ok if row["language"] == language], key) for key in metric_keys}
            for language in ("zh", "en")
        },
        "latency_seconds": {
            "all_samples": stats(times),
            "without_over_300s_for_analysis_only": stats([value for value in times if value <= args.outlier_seconds]),
            "outlier_threshold": args.outlier_seconds,
            "outliers_retained": [{"id": row["id"], "wall_seconds": row["wall_seconds"]} for row in outliers],
        },
        "observability": {
            "trace_coverage": f"{len(traces)}/{len(ok)}",
            "stage_timings_ms": stage_stats,
            "llm_calls": stats(llm_calls),
            "embedding_calls": stats(embedding_calls),
            "rerank_calls": stats(rerank_calls),
            "total_tokens_known": stats(total_tokens),
            "token_coverage": f"{len(total_tokens)}/{len(traces)}",
            "fallback_counts": dict(sorted(fallback_counts.items())),
            "retry_count": sum(int(trace.get("retry_count", 0)) for trace in traces),
            "timeout_count": sum(int(trace.get("timeout_count", 0)) for trace in traces),
        },
    }
    write_json(ROOT / args.out, {"summary": summary, "per_question": rows})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["completion"]["complete"] and len(traces) == len(ok) else 2


if __name__ == "__main__":
    raise SystemExit(main())
