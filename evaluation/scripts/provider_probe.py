#!/usr/bin/env python3
"""Probe the direct OpenAI-compatible provider endpoints used by Baseline V1."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))

from answer.config import QASettings  # noqa: E402
from answer.utils import get_openai_client, resolve_model_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="answer/configs/baseline_v1.yaml")
    parser.add_argument("--out", default="evaluation/results/baseline_v1/preflight/provider_probe.json")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    settings = QASettings.load(config_path)
    roles = {
        "answer": settings.llm,
        "rewrite": settings.rewrite_llm,
        "judge": settings.judge_llm,
    }
    result = {
        "schema_version": "direct-provider-preflight-v1",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": str(config_path.relative_to(ROOT)),
        "provider_mode": "direct",
        "credential_recorded": False,
        "roles": {},
        "status": "pass",
    }

    for role, endpoint in roles.items():
        model = resolve_model_name(endpoint.env_file, endpoint.model_name, endpoint.model_name_env)
        row = {
            "status": "not_run",
            "model": model,
            "host": None,
            "latency_ms": None,
            "response_nonempty": False,
            "token_usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
            "error": None,
        }
        started = time.monotonic()
        try:
            client = get_openai_client(endpoint.env_file, endpoint.api_key_env, endpoint.base_url_env)
            row["host"] = urlparse(str(client.base_url)).hostname
            response = client.with_options(timeout=args.timeout, max_retries=0).chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with ok only."}],
                temperature=0.0,
                max_tokens=512,
            )
            content = (response.choices[0].message.content or "").strip()
            row["response_nonempty"] = bool(content)
            usage = getattr(response, "usage", None)
            if usage is not None:
                row["token_usage"] = {
                    "input_tokens": getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
            row["status"] = "pass" if content else "fail"
            if not content:
                row["error"] = "empty_completion"
        except Exception as exc:
            row["status"] = "fail"
            row["error"] = f"{type(exc).__name__}: provider request unavailable or timed out"
        row["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
        result["roles"][role] = row
        if row["status"] != "pass":
            result["status"] = "fail"
        print(f"{role}: {row['status']} model={model} latency_ms={row['latency_ms']}", flush=True)

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
