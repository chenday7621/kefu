"""Per-thread retrieval trace state used by Baseline V1 instrumentation."""
from __future__ import annotations

import threading
from typing import Any


_local = threading.local()


def reset() -> dict[str, Any]:
    trace = {
        "timings_ms": {name: 0.0 for name in ("embedding", "dense", "bm25", "fusion", "rerank")},
        "calls": {"embedding": 0, "dense": 0, "bm25": 0, "rerank": 0},
        "status": {
            "embedding": "not_run", "dense": "not_run", "bm25": "not_run",
            "fusion": "not_run", "rerank": "not_run",
        },
        "cache": {"corpus": "unknown", "bm25": "unknown"},
        "fallbacks": [],
        "models": {},
        "retry_count": 0,
        "timeout_count": 0,
    }
    _local.trace = trace
    return trace


def current() -> dict[str, Any]:
    return getattr(_local, "trace", None) or reset()


def add_time(name: str, milliseconds: float) -> None:
    trace = current()
    trace["timings_ms"][name] = round(trace["timings_ms"].get(name, 0.0) + milliseconds, 3)


def increment(name: str) -> None:
    trace = current()
    trace["calls"][name] = trace["calls"].get(name, 0) + 1


def set_status(name: str, status: str) -> None:
    current()["status"][name] = status


def set_model(stage: str, model: str) -> None:
    current()["models"][stage] = model


def record_retry() -> None:
    current()["retry_count"] += 1


def record_timeout() -> None:
    current()["timeout_count"] += 1
