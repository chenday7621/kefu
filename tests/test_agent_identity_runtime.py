"""Offline instrumentation gates; real provider gate lives in the train runner."""
import json
import os
from pathlib import Path
import subprocess
import sys

from kefu_runtime.identity_monitor import AgentIdentityMonitor
from kefu_runtime.models import AgentTrace
from kefu_runtime.tools import ToolRegistry, ToolSpec


def test_monitor_validation_entry_and_trace_snapshot():
    m = AgentIdentityMonitor()
    trace = AgentTrace(case_id='x', benchmark='local')
    m.bind_trace(trace)
    registry = ToolRegistry(identity_monitor=m)
    registry.register(ToolSpec('read', input_schema={'required': ['id'], 'properties': {'id': {'type': 'string'}}}), lambda **kw: 1)
    assert registry.validate('missing', {}).error == 'UNKNOWN_TOOL'
    assert registry.validate('read', {}).error.startswith('INVALID_ARGUMENTS')
    assert registry.validate('read', {'id': 'x'}).error is None
    assert m.kefu_registry_validations == 3
    assert m.official_environment_results == 0
    assert json.loads(json.dumps(trace.to_dict()))['agent_identity'] == m.snapshot()
    # A local executor is not an official environment result.
    registry.execute_safe('read', {'id': 'x'})
    assert m.official_environment_results == 0


def official_offline_checks():
    from types import SimpleNamespace
    from unittest.mock import patch
    from tau2.agent.llm_agent import LLMAgent
    from tau2.orchestrator.orchestrator import Orchestrator
    from tau2.environment.environment import Environment
    from tau2.domains.retail.environment import get_environment
    from tau2.data_model.message import AssistantMessage, UserMessage, ToolCall
    from kefu_runtime.tau3_kefu_agent import build_kefu_agent_factory
    old_decision, old_response = LLMAgent.generate_next_message, Environment.get_response
    blocked = AgentIdentityMonitor()
    try:
        with blocked.guard():
            LLMAgent.generate_next_message(None, None, None)
    except RuntimeError as exc:
        assert 'Forbidden official LLMAgent' in str(exc)
    else:
        raise AssertionError('official path was not blocked')
    assert blocked.official_llm_agent_calls == 1
    assert LLMAgent.generate_next_message is old_decision
    assert Environment.get_response is old_response

    m = AgentIdentityMonitor()
    env = get_environment()
    call = ToolCall(id='identity-test', name='list_all_product_types', arguments={}, requestor='assistant')
    answers = [AssistantMessage(role='assistant', tool_calls=[call]), AssistantMessage.text(content='Done')]
    with m.guard():
        guard = LLMAgent.generate_next_message
        # Strong Test A: official Agent would fail even independently of our hook.
        with patch.object(LLMAgent, 'generate_next_message', side_effect=AssertionError('official decision forbidden')), \
             patch('tau2.utils.llm_utils.generate', side_effect=answers) as model:
            agent = build_kefu_agent_factory()(tools=env.get_tools(), domain_policy=env.get_policy(), llm='fake')
            assert not isinstance(agent, LLMAgent)
            state = agent.get_init_state()
            msg, state = agent.generate_next_message(UserMessage(role='user', content='List products'), state)
            assert m.kefu_model_decisions == 1 and m.kefu_registry_validations == 1
            assert m.official_environment_results == 0  # validation never executes
            result = Orchestrator._execute_tool_calls(SimpleNamespace(environment=env, num_errors=0), msg.tool_calls)[0]
            assert m.official_environment_results == 1
            # Same official method outside live orchestrator scope represents
            # scorer/reference replay and must not be counted.
            env.get_response(call)
            assert m.official_environment_results == 1
            agent.generate_next_message(result, state)
            assert model.call_count == 2
            assert state.messages[-2].id == call.id
            assert agent.kefu_trace.agent_identity == m.snapshot()
        assert LLMAgent.generate_next_message is guard
    assert m.snapshot() == dict(official_llm_agent_calls=0, kefu_model_decisions=2, kefu_registry_validations=1, official_environment_results=1)
    assert LLMAgent.generate_next_message is old_decision
    assert Environment.get_response is old_response
    print(json.dumps({'status': 'PASS', 'checks': ['positive_forbidden_call', 'hook_restoration', 'monkeypatched_official_decision', 'kefu_provider_and_validation', 'no_double_execution', 'exclude_scorer_replay', 'observation_next_decision'], 'identity': m.snapshot()}))


def test_official_runtime_hooks_offline():
    import pytest
    root = Path(__file__).resolve().parents[1]
    external = Path(os.environ.get('TAU2_ROOT', root.parent/'tau2-bench'))
    python = external/'.venv/bin/python'
    if not python.exists():
        pytest.skip('official tau2 environment unavailable')
    env = dict(os.environ, PYTHONPATH=str(root/'src'))
    result = subprocess.run([str(python), str(Path(__file__).resolve()), '--official'], cwd=external, env=env, text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "PASS"' in result.stdout


if __name__ == '__main__':
    official_offline_checks()
