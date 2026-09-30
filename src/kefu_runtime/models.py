"""Benchmark-neutral serializable data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@dataclass
class NormalizedCase:
    case_id: str
    benchmark: str
    domain: str | None = None
    user_input: str = ""
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    reference: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    expected_tools: list[str] = field(default_factory=list)
    expected_state: dict[str, Any] | None = None
    split: str | None = None
    runtime_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NormalizedCase":
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: value[k] for k in fields if k in value})



@dataclass
class AgentAction:
    type: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass
class ToolResult:
    tool_name: str
    tool_call_id: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    elapsed_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass
class AgentTrace:
    case_id: str
    benchmark: str
    started_at: str | None = None
    finished_at: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    retrieval_events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_answer: Any = None
    error: str | None = None
    latency_ms: float | None = None
    token_usage: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    agent_identity: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class Metrics:
    metrics: dict[str, Any] = field(default_factory=dict)
    case_count: int = 0
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))
