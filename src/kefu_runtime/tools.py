"""Benchmark-neutral tool registry with safe validation and observations."""
from __future__ import annotations
from dataclasses import dataclass
import time
from typing import Any, Callable
from .models import AgentTrace, ToolResult

class ToolValidationError(ValueError):
    code = "INVALID_ARGUMENTS"

@dataclass
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None

class ToolRegistry:
    def __init__(self, identity_monitor=None):
        self.identity_monitor = identity_monitor
        self._handlers: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}
    def register(self, spec: ToolSpec, handler: Callable[..., Any]) -> None:
        self._handlers[spec.name] = (spec, handler)
    def get(self, name: str) -> ToolSpec | None:
        item = self._handlers.get(name)
        return item[0] if item else None
    def list(self) -> list[ToolSpec]:
        return [v[0] for v in self._handlers.values()]
    def specs(self) -> list[ToolSpec]:
        return self.list()
    def schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": s.name, "description": s.description, "parameters": s.input_schema or {"type": "object", "properties": {}}}} for s in self.list()]
    def _validate(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        schema = spec.input_schema or {}
        if not isinstance(arguments, dict):
            raise ToolValidationError("arguments must be an object")
        required = schema.get("required", [])
        missing = [k for k in required if k not in arguments]
        if missing:
            raise ToolValidationError(f"missing required arguments: {', '.join(missing)}")
        properties = schema.get("properties", {})
        unknown = [k for k in arguments if k not in properties and schema.get("additionalProperties") is False]
        if unknown:
            raise ToolValidationError(f"unknown arguments: {', '.join(unknown)}")
        for key, value in arguments.items():
            expected = properties.get(key, {}).get("type")
            if expected == "string" and not isinstance(value, str): raise ToolValidationError(f"{key} must be string")
            if expected == "array" and not isinstance(value, list): raise ToolValidationError(f"{key} must be array")
            if expected == "object" and not isinstance(value, dict): raise ToolValidationError(f"{key} must be object")
            if expected == "number" and (not isinstance(value, (int,float)) or isinstance(value,bool)): raise ToolValidationError(f"{key} must be number")
    def validate(self, name: str, arguments: dict[str, Any], *, tool_call_id: str | None = None, trace: AgentTrace | None = None) -> ToolResult:
        """Validate an action without executing it (external executor mode)."""
        if self.identity_monitor is not None:
            self.identity_monitor.record("kefu_registry_validations", tool_name=name, tool_call_id=tool_call_id)
        started = time.perf_counter()
        spec = self.get(name)
        if spec is None:
            result = ToolResult(name, tool_call_id, arguments, error="UNKNOWN_TOOL")
        else:
            try:
                self._validate(spec, arguments)
                result = ToolResult(name, tool_call_id, arguments, metadata={"validation_status": "VALID"})
            except ToolValidationError as exc:
                result = ToolResult(name, tool_call_id, arguments, error=f"INVALID_ARGUMENTS: {exc}", metadata={"validation_status": "INVALID"})
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        if trace is not None:
            if self.identity_monitor is None:
                trace.metadata["kefu_tool_validations"] = trace.metadata.get("kefu_tool_validations", 0) + 1
            trace.tool_calls.append({"tool_call_id": tool_call_id, "tool_name": name, "arguments": arguments, "validation_status": "INVALID" if result.error else "VALID"})
        return result
    def execute_safe(self, name: str, arguments: dict[str, Any], *, tool_call_id: str | None = None, trace: AgentTrace | None = None) -> ToolResult:
        started=time.perf_counter(); spec=self.get(name)
        if spec is None:
            result=ToolResult(name,tool_call_id,arguments,error="UNKNOWN_TOOL")
        else:
            try:
                self._validate(spec,arguments)
                value=self._handlers[name][1](**arguments)
                result=ToolResult(name,tool_call_id,arguments,result=value)
            except ToolValidationError as exc:
                result=ToolResult(name,tool_call_id,arguments,error=f"INVALID_ARGUMENTS: {exc}")
            except Exception as exc:
                result=ToolResult(name,tool_call_id,arguments,error=f"TOOL_EXECUTION_ERROR: {type(exc).__name__}: {exc}")
        result.elapsed_ms=round((time.perf_counter()-started)*1000,3)
        if trace:
            trace.tool_calls.append({"tool_call_id":tool_call_id,"tool_name":name,"name":name,"arguments":arguments})
            trace.tool_results.append(result.to_dict())
        return result
    def execute(self, name: str, arguments: dict[str, Any], trace: AgentTrace | None = None) -> Any:
        result=self.execute_safe(name,arguments,trace=trace)
        if result.error: raise RuntimeError(result.error)
        return result.result
