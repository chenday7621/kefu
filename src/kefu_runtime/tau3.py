"""Optional tau³-bench Retail bridge; no dependency is required for unit tests."""
from __future__ import annotations

from typing import Any
from pathlib import Path
import sys

from .models import NormalizedCase


class Tau3Unavailable(RuntimeError):
    pass


class Tau3RetailAdapter:
    benchmark = "tau3_retail"

    def __init__(self, environment: Any | None = None) -> None:
        self.environment = environment

    @staticmethod
    def availability() -> dict[str, Any]:
        try:
            import tau2  # type: ignore  # official tau³-bench package namespace
        except ImportError:
            return {"available": False, "package": "tau2-bench", "reason": "official tau³-bench package (tau2) is not installed"}
        return {"available": True, "package": "tau2-bench", "version": getattr(tau2, "__version__", None)}

    def load_cases(self, *, limit: int | None = None):
        if self.environment is None:
            raise Tau3Unavailable("inject the official tau³-bench Retail environment to load interactive tasks")
        raise Tau3Unavailable("pass the official task/environment objects through load_official_cases")

    def load_official_cases(self, tau2_root: str | Path, *, limit: int | None = None):
        """Load official Retail tasks without copying tau2 into this repository."""
        root = str(Path(tau2_root).resolve() / "src")
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from tau2.domains.retail.environment import get_tasks
        except ImportError as exc:
            raise Tau3Unavailable(f"cannot import tau2 from {tau2_root}: {exc}") from exc
        tasks = get_tasks("base")
        return [self.case_from_task(task, case_id=str(task.id)) for task in (tasks[:limit] if limit is not None else tasks)]


    def register_environment_tools(self, registry, environment: Any) -> int:
        """Expose official environment tools through the neutral ToolRegistry.

        The official tau2 orchestrator normally executes these tools itself; this
        method provides the same schema/forwarding boundary for the kefu loop.
        """
        from .tools import ToolSpec
        count = 0
        for tool in environment.get_tools():
            schema = getattr(tool, "openai_schema", {}) or {}
            fn = (schema.get("function") or {})
            name = str(fn.get("name") or getattr(tool, "name", ""))
            if not name:
                continue
            registry.register(ToolSpec(name=name, description=str(fn.get("description", "")), input_schema=fn.get("parameters") or {}), lambda _tool=tool, **kwargs: environment.use_tool(_tool.name, **kwargs))
            count += 1
        return count

    def case_from_task(self, task: Any, *, case_id: str, domain: str = "retail") -> NormalizedCase:
        """Translate an official task while retaining interactive state and criteria."""
        raw = task.model_dump(mode="json") if hasattr(task, "model_dump") else dict(task)
        instructions = ((raw.get("user_scenario") or {}).get("instructions") or {})
        user_input = instructions.get("reason_for_call") or raw.get("instruction") or raw.get("user_input") or ""
        actions = ((raw.get("evaluation_criteria") or {}).get("actions") or [])
        expected_tools = [str(a.get("name")) for a in actions if a.get("name")]
        return NormalizedCase(
            case_id=case_id, benchmark=self.benchmark, domain=domain,
            user_input=str(user_input),
            metadata={"adapter": "tau3_retail", "official_task": raw},
            runtime_context={"task": raw}, expected_tools=expected_tools,
            expected_state=raw.get("initial_state"),
        )
