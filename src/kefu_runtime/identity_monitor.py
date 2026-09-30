"""Scoped identity instrumentation, independent of Agent decisions and policies.

The official decision hook is process-wide and intentionally restricted to a
serial gate. Environment counts exclude evaluator replay and user tool calls.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any
from unittest.mock import patch

_ACTIVE = ContextVar('kefu_identity_monitor', default=None)
_LIVE_ENV = ContextVar('kefu_live_environment', default=None)


@dataclass
class AgentIdentityMonitor:
    official_llm_agent_calls: int = 0
    kefu_model_decisions: int = 0
    kefu_registry_validations: int = 0
    official_environment_results: int = 0
    hook_installed: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    _traces: list[Any] = field(default_factory=list, repr=False)

    @classmethod
    def current(cls):
        return _ACTIVE.get()

    def snapshot(self):
        return {name: getattr(self, name) for name in (
            'official_llm_agent_calls', 'kefu_model_decisions',
            'kefu_registry_validations', 'official_environment_results')}

    def bind_trace(self, trace):
        self._traces.append(trace)
        self._sync()

    def _sync(self):
        for trace in self._traces:
            trace.agent_identity = self.snapshot()
            trace.metadata.update({
                'official_llm_agent_decision_calls': self.official_llm_agent_calls,
                'kefu_model_decisions': self.kefu_model_decisions,
                'kefu_tool_validations': self.kefu_registry_validations,
                'official_environment_tool_results': self.official_environment_results,
                'identity_hook_installed': self.hook_installed,
            })

    def record(self, counter, **evidence):
        if counter not in self.snapshot():
            raise ValueError(f'Unknown identity counter: {counter}')
        setattr(self, counter, getattr(self, counter) + 1)
        self.events.append({'event_index': len(self.events), 'counter': counter, **evidence})
        self._sync()

    @contextmanager
    def guard(self):
        """Block official Agent decisions; observe actual live environment calls.

        Hooks are removed even on failure. No provider/scorer/user code is patched.
        Environment.get_response runs exactly once; only completed live assistant
        responses (including explicit tool-error observations) count as results.
        """
        from tau2.agent.llm_agent import LLMAgent
        from tau2.environment.environment import Environment
        from tau2.orchestrator.orchestrator import Orchestrator
        if _ACTIVE.get() is not None:
            raise RuntimeError('Nested identity guards are unsupported')
        original_execute = Orchestrator._execute_tool_calls
        original_response = Environment.get_response
        monitor = self

        def forbidden(*args, **kwargs):
            monitor.record('official_llm_agent_calls', entry='LLMAgent.generate_next_message')
            raise RuntimeError('Forbidden official LLMAgent decision path detected')

        @wraps(original_execute)
        def execute(orchestrator, tool_calls):
            token = _LIVE_ENV.set(orchestrator.environment)
            try:
                return original_execute(orchestrator, tool_calls)
            finally:
                _LIVE_ENV.reset(token)

        @wraps(original_response)
        def response(environment, tool_call):
            result = original_response(environment, tool_call)
            if _LIVE_ENV.get() is environment and tool_call.requestor == 'assistant':
                monitor.record('official_environment_results', tool_call_id=tool_call.id,
                               tool_name=tool_call.name, error_present=result.error)
            return result

        token = _ACTIVE.set(self)
        try:
            with patch.object(LLMAgent, 'generate_next_message', forbidden), \
                 patch.object(Orchestrator, '_execute_tool_calls', execute), \
                 patch.object(Environment, 'get_response', response):
                self.hook_installed = True
                self._sync()
                yield self
        finally:
            _ACTIVE.reset(token)
