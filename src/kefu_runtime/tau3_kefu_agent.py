"""Independent Kefu transactional agent for official tau2 half-duplex protocol."""
from __future__ import annotations
from typing import Any, Optional
from .models import AgentTrace
from .tools import ToolRegistry, ToolSpec
from .identity_monitor import AgentIdentityMonitor

class KefuTau3Unavailable(RuntimeError):
    pass

def build_kefu_agent_factory(trace_sink: list[AgentTrace] | None = None):
    try:
        from pydantic import BaseModel
        from tau2.agent.base.llm_config import LLMConfigMixin
        from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage, is_valid_agent_history_message
        from tau2.data_model.message import AssistantMessage, Message, MultiToolMessage, SystemMessage, ToolMessage
        from tau2.utils.llm_utils import generate
    except ImportError as exc:
        raise KefuTau3Unavailable(f"tau2 environment is required: {exc}") from exc

    class KefuAgentState(BaseModel):
        system_messages: list[SystemMessage]
        messages: list[Any]

    class KefuTau2Agent(LLMConfigMixin, HalfDuplexAgent[KefuAgentState]):
        """Kefu decision engine; never delegates decisions to tau2 LLMAgent."""
        AGENT_INSTRUCTION = """You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only."""
        def __init__(self, *, tools, domain_policy, llm, llm_args=None, decision_limit: int = 15):
            super().__init__(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
            self.decision_limit = decision_limit
            self.identity_monitor = AgentIdentityMonitor.current() or AgentIdentityMonitor()
            self.kefu_trace = AgentTrace(case_id="", benchmark="tau3_retail", metadata={
                "mode":"transactional", "decision_engine":"kefu_tool_loop", "tool_registry":"kefu",
                "tool_executor":"tau2_official_environment",
                "task_elapsed_ms": None, "model_elapsed_ms": None, "tool_elapsed_ms": None, "scorer_elapsed_ms": None,
                "prompt_tokens": None, "completion_tokens": None, "total_tokens": None})
            self.identity_monitor.bind_trace(self.kefu_trace)
            self.registry = ToolRegistry(identity_monitor=self.identity_monitor)
            for tool in tools:
                schema = getattr(tool, "openai_schema", {}) or {}; fn = schema.get("function", {})
                self.registry.register(ToolSpec(name=str(fn.get("name") or getattr(tool,"name","")), description=str(fn.get("description","")), input_schema=fn.get("parameters") or {}), lambda **kwargs: kwargs)
        @property
        def system_prompt(self):
            return f"<instructions>\n{self.AGENT_INSTRUCTION}\n</instructions>\n<policy>\n{self.domain_policy}\n</policy>"
        def get_init_state(self, message_history: Optional[list[Message]] = None):
            history=list(message_history or []); assert all(is_valid_agent_history_message(m) for m in history)
            return KefuAgentState(system_messages=[SystemMessage(role="system", content=self.system_prompt)], messages=history)
        def _record(self, message: Any, direction: str):
            try: value=message.model_dump(mode="json")
            except Exception: value={"role":getattr(message,"role",direction),"content":str(message)}
            value["direction"]=direction; self.kefu_trace.messages.append(value)
            if isinstance(message,(ToolMessage,MultiToolMessage)):
                items=message.tool_messages if isinstance(message,MultiToolMessage) else [message]
                for item in items:
                    call_name = next((c.get("tool_name") for c in self.kefu_trace.tool_calls if c.get("tool_call_id") == item.id), None)
                    self.kefu_trace.tool_results.append({"tool_call_id":item.id,"tool_name":call_name,"result":item.content,"error_present":bool(item.error),"error_type":"OFFICIAL_TOOL_ERROR" if item.error else None,"error_message":item.content if item.error else None,"elapsed_ms":None,"step":self.kefu_trace.metadata.get("kefu_model_decisions",0)})
        def generate_next_message(self, message: ValidAgentInputMessage, state: KefuAgentState):
            self._record(message,"input")
            state.messages.extend(message.tool_messages if isinstance(message,MultiToolMessage) else [message])
            if self.kefu_trace.metadata["kefu_model_decisions"] >= self.decision_limit: raise RuntimeError("KEFU_MODEL_DECISION_LIMIT")
            import time
            started=time.perf_counter()
            self.identity_monitor.record("kefu_model_decisions", entry="provider.generate")
            assistant=generate(model=self.llm, tools=self.tools, messages=state.system_messages+state.messages, call_name="kefu_agent_response", **self.llm_args)
            self.kefu_trace.metadata["model_elapsed_ms_last"]=round((time.perf_counter()-started)*1000,3); self.kefu_trace.metadata["model_elapsed_ms"]=self.kefu_trace.metadata["model_elapsed_ms_last"]
            usage = getattr(assistant, "usage", None) or {}
            if isinstance(usage, dict):
                self.kefu_trace.metadata["prompt_tokens"] = usage.get("prompt_tokens")
                self.kefu_trace.metadata["completion_tokens"] = usage.get("completion_tokens")
                self.kefu_trace.metadata["total_tokens"] = usage.get("total_tokens")
            for call in assistant.tool_calls or []:
                args=call.arguments if isinstance(call.arguments,dict) else {}
                validation=self.registry.validate(call.name,args,tool_call_id=call.id,trace=self.kefu_trace)
                if validation.error:
                    self.kefu_trace.error=validation.error; assistant=AssistantMessage.text(content=f"I could not validate that action: {validation.error}"); break
            state.messages.append(assistant); self._record(assistant,"output")
            if assistant.content: self.kefu_trace.final_answer=assistant.content
            return assistant,state
    def factory(*, tools, domain_policy, llm=None, llm_args=None, **kwargs):
        agent=KefuTau2Agent(tools=tools,domain_policy=domain_policy,llm=llm,llm_args=llm_args)
        if trace_sink is not None: trace_sink.append(agent.kefu_trace)
        return agent
    factory.agent_class=KefuTau2Agent
    return factory
