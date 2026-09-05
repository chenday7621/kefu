#!/usr/bin/env python3
"""Run the unvalidated Baseline V1 answer Judge against Reference Schema V2.

This pipeline preserves every per-item input and raw model output. Its scores must
remain labelled UNVALIDATED_JUDGE_METRIC until human calibration is completed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline_v1_common import load_jsonl, sha256_file  # noqa: E402


PROMPT_PATH = ROOT / "evaluation" / "judge" / "prompts" / "answer_judge_v1.txt"
DIMENSIONS = ("answer_correctness", "completeness", "faithfulness")


def evidence_text(reference: dict[str, Any]) -> str:
    blocks = []
    for index, item in enumerate(reference.get("evidence") or [], 1):
        text = item.get("text")
        if not text:
            continue
        label = item.get("chunk_id") or item.get("source_location") or f"evidence-{index}"
        blocks.append(f"[{label}]\n{text}")
    return "\n\n---\n\n".join(blocks) if blocks else "(SOURCE_EVIDENCE_UNAVAILABLE)"


def build_prompt(reference: dict[str, Any], system_answer: str) -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").format(
        question=reference["question"],
        reference_answer=reference.get("reference_answer") or "(REFERENCE_ANSWER_UNAVAILABLE)",
        evidence=evidence_text(reference),
        system_answer=system_answer,
    )


def parse_scores(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start:end + 1])
    parsed = {}
    for name in DIMENSIONS:
        item = value.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"missing object: {name}")
        score = item.get("score")
        if not isinstance(score, (int, float)) or not 1 <= float(score) <= 5:
            raise ValueError(f"invalid score for {name}: {score!r}")
        parsed[name] = {"score": float(score), "reason": str(item.get("reason") or "")}
    return parsed


def usage_dict(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def load_latest_raw(path: Path) -> dict[str, dict[str, Any]]:
    latest = {}
    for row in load_jsonl(path):
        latest[str(row["id"])] = row
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--references", default="evaluation/gold_v2/references.jsonl")
    parser.add_argument("--out", required=True)
    parser.add_argument("--split", choices=("train", "dev", "heldout"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", help="validate inputs without model calls")
    args = parser.parse_args()

    raw_path, reference_path, out_path = ROOT / args.raw, ROOT / args.references, ROOT / args.out
    references = {str(row["id"]): row for row in load_jsonl(reference_path)}
    latest = load_latest_raw(raw_path)
    done: set[str] = set()
    if out_path.exists():
        for row in load_jsonl(out_path):
            if row.get("parse_status") == "ok":
                done.add(str(row["id"]))
    todo = []
    for qid, row in latest.items():
        ref = references.get(qid)
        if not ref or qid in done or row.get("error") or not row.get("qa_result"):
            continue
        if ref["quality_status"] == "quarantined" or (args.split and ref.get("split") != args.split):
            continue
        todo.append((qid, row, ref))
    todo.sort(key=lambda item: int(item[0]) if item[0].isdigit() else item[0])
    if args.limit is not None:
        todo = todo[:args.limit]
    print(f"judge_plan={len(todo)} split={args.split or 'all'} status=UNVALIDATED_JUDGE_METRIC")
    if args.dry_run:
        for qid, row, ref in todo[:3]:
            build_prompt(ref, row["qa_result"]["final_answer"].get("content", ""))
        return 0

    sys.path.insert(0, str(ROOT / "answer" / "src"))
    from answer.config import QASettings
    from answer.utils import get_openai_client, resolve_model_name

    settings = QASettings.load()
    endpoint = settings.judge_llm
    client = get_openai_client(endpoint.env_file, endpoint.api_key_env, endpoint.base_url_env)
    model = resolve_model_name(endpoint.env_file, endpoint.model_name, endpoint.model_name_env)
    prompt_hash = sha256_file(PROMPT_PATH)
    failure_count = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8", newline="\n") as output:
        for index, (qid, row, reference) in enumerate(todo, 1):
            system_answer = row["qa_result"]["final_answer"].get("content", "")
            prompt = build_prompt(reference, system_answer)
            record: dict[str, Any] = {
                "id": qid,
                "trace_id": str(uuid.uuid4()),
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "metric_status": "UNVALIDATED_JUDGE_METRIC",
                "question": reference["question"],
                "reference_answer": reference.get("reference_answer"),
                "gold_evidence": reference.get("evidence"),
                "system_answer": system_answer,
                "judge_raw_response": None,
                "parsed_scores": None,
                "parse_status": "not_started",
                "error": None,
                "model": model,
                "prompt_version": "answer_judge_v1",
                "prompt_sha256": prompt_hash,
                "token_usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
                "latency_ms": None,
                "evidence_status": "available" if evidence_text(reference) != "(SOURCE_EVIDENCE_UNAVAILABLE)" else "unavailable",
            }
            started = time.monotonic()
            try:
                response = client.with_options(timeout=120).chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=2048,
                )
                raw = (response.choices[0].message.content or "").strip()
                record["judge_raw_response"] = raw
                record["token_usage"] = usage_dict(response)
                record["parsed_scores"] = parse_scores(raw)
                record["parse_status"] = "ok"
            except Exception as exc:
                record["parse_status"] = "error"
                record["error"] = f"{type(exc).__name__}: {exc}"
                failure_count += 1
            record["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            output.flush()
            print(f"[{index}/{len(todo)}] id={qid} {record['parse_status']}", flush=True)
    return 0 if failure_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
