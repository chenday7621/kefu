"""Thread-safe per-query telemetry for the formal Baseline V1 protocol."""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator


STAGES = (
    "router", "rewrite", "decompose", "reload", "embedding", "dense", "bm25",
    "fusion", "rerank", "kg", "small_generation", "mid_generation",
    "big_generation", "ensemble",
)


class TraceRecorder:
    def __init__(self, *, concurrency: int = 1) -> None:
        self.trace_id = str(uuid.uuid4())
        self.root_worker_id = threading.get_ident()
        self.concurrency = concurrency
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self.timings_ms = {stage: 0.0 for stage in STAGES}
        self.stage_status = {stage: "not_run" for stage in STAGES}
        self.model_calls: list[dict[str, Any]] = []
        self.fallbacks: list[str] = []
        self.cache = {"corpus": "unknown", "bm25": "unknown", "gateway": "unreported"}
        self.models: dict[str, str] = {}
        self.timeout_count = 0
        self.retry_count = 0
        self.embedding_calls = 0
        self.rerank_calls = 0

    @contextmanager
    def stage(self, name: str, *, skipped_status: str | None = None) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        except Exception:
            with self._lock:
                self.stage_status[name] = "error"
            raise
        else:
            with self._lock:
                self.stage_status[name] = skipped_status or "ok"
        finally:
            with self._lock:
                self.timings_ms[name] = round(self.timings_ms.get(name, 0.0) + (time.monotonic() - started) * 1000, 3)

    def mark(self, name: str, status: str, *, milliseconds: float | None = None) -> None:
        with self._lock:
            self.stage_status[name] = status
            if milliseconds is not None:
                self.timings_ms[name] = round(self.timings_ms.get(name, 0.0) + milliseconds, 3)

    def model_call(self, *, stage: str, model: str, elapsed_ms: float, response: Any = None,
                   error: Exception | None = None, attempt: int = 1) -> None:
        usage = getattr(response, "usage", None)
        item = {
            "stage": stage,
            "model": model,
            "worker_id": threading.get_ident(),
            "attempt": attempt,
            "latency_ms": round(elapsed_ms, 3),
            "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
            "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
            "status": "error" if error else "ok",
            "error_type": type(error).__name__ if error else None,
        }
        with self._lock:
            self.model_calls.append(item)
            if attempt > 1:
                self.retry_count += 1
            if error and "timeout" in f"{type(error).__name__}: {error}".lower():
                self.timeout_count += 1

    def absorb_retrieval(self, meta: Any) -> None:
        value = meta.to_dict() if hasattr(meta, "to_dict") else dict(meta or {})
        with self._lock:
            for name, milliseconds in (value.get("stage_timings_ms") or {}).items():
                self.timings_ms[name] = round(self.timings_ms.get(name, 0.0) + float(milliseconds or 0), 3)
            for name, status in (value.get("stage_status") or {}).items():
                self.stage_status[name] = status
            calls = value.get("call_counts") or {}
            self.embedding_calls += int(calls.get("embedding", 0))
            self.rerank_calls += int(calls.get("rerank", 0))
            self.retry_count += int(value.get("retry_count", 0))
            self.timeout_count += int(value.get("timeout_count", 0))
            self.models.update(value.get("model_names") or {})
            self.cache.update(value.get("cache_status") or {})
            self.fallbacks.extend(value.get("fallbacks") or [])

    def fallback(self, name: str) -> None:
        with self._lock:
            self.fallbacks.append(name)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            known_input = [v["input_tokens"] for v in self.model_calls if isinstance(v["input_tokens"], int)]
            known_output = [v["output_tokens"] for v in self.model_calls if isinstance(v["output_tokens"], int)]
            return {
                "schema_version": "query-trace-v1",
                "trace_id": self.trace_id,
                "worker_id": self.root_worker_id,
                "concurrency": self.concurrency,
                "stage_timings_ms": dict(self.timings_ms),
                "stage_status": dict(self.stage_status),
                "calls": {
                    "llm": len(self.model_calls),
                    "embedding": self.embedding_calls,
                    "rerank": self.rerank_calls,
                },
                "tokens": {
                    "input": sum(known_input) if known_input else None,
                    "output": sum(known_output) if known_output else None,
                    "total": sum(known_input) + sum(known_output) if known_input and known_output else None,
                    "coverage": f"{len(known_input)}/{len(self.model_calls)}",
                },
                "model_calls": list(self.model_calls),
                "models": {
                    **dict(self.models),
                    "llm_by_stage": {
                        stage: sorted({call["model"] for call in self.model_calls if call["stage"] == stage})
                        for stage in sorted({call["stage"] for call in self.model_calls})
                    },
                },
                "fallbacks": sorted(set(self.fallbacks)),
                "degraded_mode": bool(self.fallbacks),
                "cache": dict(self.cache),
                "retry_count": self.retry_count,
                "timeout_count": self.timeout_count,
                "total_ms": round((time.monotonic() - self.started) * 1000, 3),
            }
