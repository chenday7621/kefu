import json
from pathlib import Path
import pytest
from kefu_runtime.models import AgentTrace, NormalizedCase
from kefu_runtime.tools import ToolRegistry, ToolSpec
from kefu_runtime.tool_loop import ToolLoop
from evaluation.metrics import summarize_rewards
from evaluation.runner import verify

def test_serialization():
    case = NormalizedCase(case_id="example", benchmark="synthetic")
    assert NormalizedCase.from_dict(json.loads(json.dumps(case.to_dict()))) == case
    assert json.loads(json.dumps(AgentTrace("example", "synthetic").to_dict()))["token_usage"] is None

def test_external_validation_never_executes():
    calls = []
    r = ToolRegistry()
    r.register(ToolSpec("lookup", input_schema={"required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False}), lambda **kw: calls.append(kw))
    assert r.validate("lookup", {"id": "example"}).error is None
    assert not calls
    assert r.validate("missing", {}).error == "UNKNOWN_TOOL"
    assert r.validate("lookup", {}).error.startswith("INVALID_ARGUMENTS")
    assert r.validate("lookup", {"id": 42}).error.startswith("INVALID_ARGUMENTS")
    assert r.validate("lookup", {"id": "x", "extra": 1}).error.startswith("INVALID_ARGUMENTS")

def test_tool_loop_observation():
    r = ToolRegistry(); r.register(ToolSpec("echo", input_schema={"properties": {"value": {"type": "string"}}}), lambda value: value)
    seen = []
    def model(**kw):
        seen.append(kw)
        if len(seen) == 1:
            return {"tool_calls": [{"id": "example", "function": {"name": "echo", "arguments": {"value": "hello"}}}]}
        assert kw["messages"][-1]["role"] == "tool"
        return {"content": "done"}
    answer, trace = ToolLoop(model, r).run([])
    assert answer == "done" and len(trace.tool_results) == 1

def test_official_metric_aggregation():
    assert summarize_rewards([1, 0, 1])["task_success_rate"] == 2/3
    with pytest.raises(ValueError): summarize_rewards([])
    with pytest.raises(ValueError): summarize_rewards([None])

def test_public_evidence():
    assert verify(Path(__file__).resolve().parents[1])["status"] == "PASS"
