"""Pre-flight gateway health check for baseline runs.

Exits 0 only if the litellm gateway is alive AND the exact model alias the
answer layer uses returns a real completion. Exits 2 otherwise, so pipeline
scripts can abort before burning hours against a dead upstream.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))

from answer.config import QASettings  # noqa: E402
from answer.utils import get_openai_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    result = {
        "schema_version": "gateway-preflight-v1",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gateway_liveliness": "not_run",
        "completion": "not_run",
        "model_alias": None,
        "error": None,
    }

    def finish(code: int) -> int:
        if args.out:
            path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return code

    try:
        with urllib.request.urlopen("http://127.0.0.1:4000/health/liveliness", timeout=5) as r:
            if r.status != 200:
                print(f"GATEWAY PROBE FAIL: liveliness http {r.status}")
                result["gateway_liveliness"] = "fail"
                result["error"] = f"liveliness_http_{r.status}"
                return finish(2)
            result["gateway_liveliness"] = "pass"
    except Exception as exc:
        print(f"GATEWAY PROBE FAIL: liveliness unreachable: {exc}")
        result["gateway_liveliness"] = "fail"
        result["error"] = f"{type(exc).__name__}: local gateway unavailable"
        return finish(2)

    try:
        settings = QASettings.load()
        client = get_openai_client(settings.llm.env_file,
                                   settings.llm.api_key_env, settings.llm.base_url_env)
        model = settings.llm.model_name or "qwen3-max"
        result["model_alias"] = model
        resp = client.with_options(timeout=args.timeout, max_retries=0).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "回复 ok 两个字母即可"}],
            temperature=0.0,
            max_tokens=512,  # reasoning model needs headroom before content
        )
        content = (resp.choices[0].message.content or "").strip()
        if not content:
            print(f"GATEWAY PROBE FAIL: empty completion from alias {model}")
            result["completion"] = "fail"
            result["error"] = "empty_completion"
            return finish(2)
        result["completion"] = "pass"
        print(f"GATEWAY PROBE OK: alias={model}")
        return finish(0)
    except Exception as exc:
        print(f"GATEWAY PROBE FAIL: completion error: {exc}")
        result["completion"] = "fail"
        result["error"] = f"{type(exc).__name__}: completion unavailable or timed out"
        return finish(2)


if __name__ == "__main__":
    sys.exit(main())
