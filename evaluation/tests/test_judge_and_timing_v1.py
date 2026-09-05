from __future__ import annotations

import json
from pathlib import Path

from answer.models import AnswerPayload
from answer.observability import STAGES, TraceRecorder
from run_judge import build_prompt, evidence_text, parse_scores
from score_judge_calibration_v1 import score_rows


ROOT = Path(__file__).resolve().parents[2]


def test_judge_uses_reference_v2_evidence_text():
    reference = next(
        json.loads(line)
        for line in (ROOT / "evaluation/gold_v2/references.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip() and any(item.get("text") for item in json.loads(line)["evidence"])
    )
    evidence = evidence_text(reference)
    assert evidence != "(SOURCE_EVIDENCE_UNAVAILABLE)"
    prompt = build_prompt(reference, "system answer")
    assert reference["question"] in prompt
    assert "system answer" in prompt
    parsed = parse_scores(json.dumps({
        "answer_correctness": {"score": 4, "reason": "r"},
        "completeness": {"score": 3, "reason": "r"},
        "faithfulness": {"score": 5, "reason": "r"},
    }))
    assert parsed["faithfulness"]["score"] == 5.0


def test_answer_payload_supports_future_citations_without_claiming_score():
    payload = AnswerPayload(
        content="answer", images=[], citation_chunk_ids=["chunk-1"],
        source_metadata=[{"manual_id": "manual-1"}],
    )
    assert payload.citation_chunk_ids == ["chunk-1"]
    prompt = (ROOT / "evaluation/judge/prompts/answer_judge_v1.txt").read_text(encoding="utf-8")
    assert "citation" not in prompt.lower()


def test_stage_timing_trace_contract():
    trace = TraceRecorder(concurrency=1)
    with trace.stage("router"):
        pass
    trace.mark("rewrite", "disabled", milliseconds=0.0)
    value = trace.to_dict()
    assert value["schema_version"] == "query-trace-v1"
    assert value["trace_id"]
    assert set(STAGES) <= set(value["stage_timings_ms"])
    assert set(STAGES) <= set(value["stage_status"])
    assert value["stage_status"]["router"] == "ok"
    assert value["stage_status"]["rewrite"] == "disabled"
    assert value["calls"] == {"llm": 0, "embedding": 0, "rerank": 0}
    assert value["models"]["llm_by_stage"] == {}
    assert value["cache"]["gateway"] == "unreported"
    assert value["retry_count"] == 0
    assert value["timeout_count"] == 0
    assert isinstance(value["total_ms"], float)


def test_calibration_metrics_are_reported_by_subset():
    human = {
        "HJ-001": {"subset": "calibration", "human_answer_correctness": "4", "human_completeness": "3", "human_faithfulness": "5", "human_binary_accept": "1"},
        "HJ-002": {"subset": "validation", "human_answer_correctness": "2", "human_completeness": "2", "human_faithfulness": "2", "human_binary_accept": "0"},
    }
    judge = {
        key: {"parsed_scores": {
            "answer_correctness": {"score": int(row["human_answer_correctness"])},
            "completeness": {"score": int(row["human_completeness"])},
            "faithfulness": {"score": int(row["human_faithfulness"])},
        }} for key, row in human.items()
    }
    result = score_rows(human, judge, subset=None)
    assert result["binary"]["agreement"] == 1.0
    assert result["binary"]["accuracy"] == 1.0
    assert result["binary"]["f1"] == 1.0
