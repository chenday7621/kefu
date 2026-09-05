from __future__ import annotations

from pathlib import Path

from answer.config import QASettings


ROOT = Path(__file__).resolve().parents[2]


def test_formal_baseline_uses_direct_dashscope_contract():
    settings = QASettings.load(ROOT / "answer/configs/baseline_v1.yaml")
    for endpoint in (settings.llm, settings.rewrite_llm, settings.judge_llm):
        assert endpoint.env_file.resolve() == (ROOT / "gateway/.env").resolve()
        assert endpoint.api_key_env == "UPSTREAM_1_API_KEY"
        assert endpoint.base_url_env == "UPSTREAM_1_BASE_URL"
        assert endpoint.model_name == "deepseek-v4-flash"


def test_litellm_profile_is_explicitly_optional():
    settings = QASettings.load(ROOT / "answer/configs/baseline_v1_litellm_optional.yaml")
    assert settings.llm.api_key_env == "INTERX_GATEWAY_API_KEY"
    assert settings.llm.base_url_env == "INTERX_GATEWAY_BASE_URL"
    assert settings.llm.model_name == "qwen3.6-plus"


def test_reproduction_preflight_uses_direct_provider():
    script = (ROOT / "scripts/reproduce_baseline_v1.sh").read_text(encoding="utf-8")
    assert "evaluation/scripts/provider_probe.py" in script
    assert "evaluation/scripts/gateway_probe.py" not in script
    assert "INTERX_GATEWAY_API_KEY" not in script
    assert "INTERX_GATEWAY_BASE_URL" not in script
