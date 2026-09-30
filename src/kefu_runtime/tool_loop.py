"""Small provider-native single-agent tool loop."""
from __future__ import annotations
import json, time
from typing import Any, Callable
from .models import AgentAction, AgentTrace
from .tools import ToolRegistry

class ToolLoop:
    def __init__(self, model_call: Callable[..., Any], registry: ToolRegistry, *, max_steps: int = 15):
        self.model_call=model_call; self.registry=registry; self.max_steps=max_steps
    @staticmethod
    def _get(value: Any, key: str, default=None):
        return value.get(key,default) if isinstance(value,dict) else getattr(value,key,default)
    def _normalize(self,response: Any) -> tuple[str|None,list[dict[str,Any]],dict[str,Any]]:
        message=self._get(response,"message",response)
        content=self._get(message,"content")
        calls=self._get(message,"tool_calls",[]) or []
        normalized=[]
        for call in calls:
            fn=self._get(call,"function",call)
            args=self._get(fn,"arguments",{})
            if isinstance(args,str):
                try: args=json.loads(args)
                except json.JSONDecodeError: args={"_raw":args}
            normalized.append({"id":self._get(call,"id",None),"name":self._get(fn,"name",None),"arguments":args})
        usage=self._get(response,"usage",None)
        return content,normalized,usage if isinstance(usage,dict) else (usage.model_dump() if hasattr(usage,"model_dump") else {})
    def run(self, messages: list[dict[str,Any]], *, trace: AgentTrace | None = None) -> tuple[str|None,AgentTrace]:
        trace=trace or AgentTrace(case_id="",benchmark="transactional")
        trace.started_at=trace.started_at or AgentTrace.now(); working=list(messages)
        for step in range(self.max_steps):
            started=time.perf_counter()
            try: response=self.model_call(messages=working,tools=self.registry.schemas())
            except Exception as exc:
                trace.error=f"MODEL_ERROR: {type(exc).__name__}: {exc}"; trace.metadata["termination_reason"]="MODEL_ERROR"; break
            content,calls,usage=self._normalize(response); trace.token_usage=usage or trace.token_usage
            if content is not None or calls:
                trace.messages.append({"role":"assistant","content":content,"tool_calls":calls,"step":step})
            if not calls:
                trace.final_answer=content; trace.metadata["termination_reason"]="FINAL_ANSWER"; break
            assistant={"role":"assistant","content":content,"tool_calls":[{"id":c["id"],"type":"function","function":{"name":c["name"],"arguments":json.dumps(c["arguments"],ensure_ascii=False)}} for c in calls]}; working.append(assistant)
            for call in calls:
                result=self.registry.execute_safe(call["name"],call["arguments"],tool_call_id=call["id"],trace=trace)
                working.append({"role":"tool","tool_call_id":call["id"],"name":call["name"],"content":json.dumps(result.to_dict(),ensure_ascii=False)})
            trace.metadata["last_step_latency_ms"]=round((time.perf_counter()-started)*1000,3)
        else:
            trace.error="MAX_STEPS"; trace.metadata["termination_reason"]="MAX_STEPS"
        trace.finished_at=AgentTrace.now(); return trace.final_answer,trace
