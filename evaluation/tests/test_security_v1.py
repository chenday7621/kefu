from __future__ import annotations

from pathlib import Path

import pytest

from chat.store import _session_path, validate_storage_id


@pytest.mark.parametrize("value", ["../escape", "a/b", "a\\b", "..", "", " space"])
def test_storage_identifier_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        validate_storage_id(value, field_name="id")


def test_resolved_session_path_stays_below_root(tmp_path):
    result = _session_path(tmp_path, "session-1", "user_1")
    assert result.is_relative_to(tmp_path.resolve())


def test_local_secret_permission_audit_passes():
    import check_secrets_v1
    assert check_secrets_v1.main() == 0


def test_gateway_verbose_logging_is_disabled_by_default():
    root = Path(__file__).resolve().parents[2]
    template = (root / "gateway/litellm/config.template.yaml").read_text(encoding="utf-8")
    builder = (root / "gateway/scripts/build_multi_upstream_config.py").read_text(encoding="utf-8")
    assert "set_verbose: false" in template
    assert "set_verbose: true" not in template
    assert "set_verbose: false" in builder
    assert "set_verbose: true" not in builder


def test_gateway_tools_do_not_embed_a_default_master_key():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "gateway/scripts/build_multi_upstream_config.py",
        root / "gateway/scripts/generate_env_from_cc_switch.py",
        root / "gateway/scripts/local_monitor.py",
        root / "gateway/scripts/routing_probe.py",
    ]
    for path in paths:
        assert "interx-local-master-key" not in path.read_text(encoding="utf-8")
