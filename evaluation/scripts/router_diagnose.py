"""Router failure diagnosis — observation only, no config change.

Replays the EXACT router call (same prompt file, temperature=0.0, timeout 10s,
model resolution identical to answer/router.py) for a few fixed questions and
records, per call:
  - raw content, finish_reason, usage tokens
  - reasoning_content / reasoning_tokens if the upstream returns them
  - whether extract_json would have succeeded (i.e. would the router have worked)

Then repeats the same call at increasing max_tokens (32 = production value,
then 256 / 1024) to isolate whether the failure is max_tokens starvation of a
reasoning model, WITHOUT touching any project config — these are standalone
diagnostic calls.

Also prints the gateway model alias table (model mapping) from the rendered
litellm config, redacting keys.

Usage:
  chat/.venv/bin/python evaluation/scripts/router_diagnose.py \
      [--out evaluation/results/baseline50/router_diagnosis.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))

from answer.config import QASettings  # noqa: E402
from answer.utils import extract_json, get_openai_client, load_prompt  # noqa: E402

QUESTIONS = [
    ("zh-manual", "空调制冷效果不太好怎么办？"),
    ("zh-manual", "如何清洗洗碗机的喷淋臂？"),
    ("en-manual", "How do I use the air fryer for the first time?"),
    ("general", "你们的人工客服几点上班？"),
    ("general", "Can I get a refund for my order?"),
]
MAX_TOKENS_LADDER = [32, 256, 1024]  # 32 == production value in router.py


def probe(client, model: str, prompt: str, max_tokens: int) -> dict:
    t0 = time.monotonic()
    out: dict = {"max_tokens": max_tokens}
    try:
        resp = client.with_options(timeout=30.0).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        msg = choice.message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None)
        usage = resp.usage
        details = getattr(usage, "completion_tokens_details", None)
        out.update({
            "finish_reason": choice.finish_reason,
            "content": content[:500],
            "content_len": len(content),
            "reasoning_content_present": reasoning is not None,
            "reasoning_content_head": (reasoning or "")[:200] or None,
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        })
        try:
            data = extract_json(content)
            out["extract_json_ok"] = True
            out["route"] = str(data.get("route"))
        except Exception as exc:
            out["extract_json_ok"] = False
            out["extract_json_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        out["call_error"] = f"{type(exc).__name__}: {exc}"
    out["elapsed_s"] = round(time.monotonic() - t0, 2)
    return out


def model_mapping() -> list[dict]:
    cfg = (ROOT / "gateway" / "litellm" / "config.yaml").read_text(encoding="utf-8")
    cfg = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-REDACTED", cfg)
    mapping, alias, target = [], None, None
    for line in cfg.splitlines():
        m = re.match(r"\s*-?\s*model_name:\s*(\S+)", line)
        if m:
            if alias:
                mapping.append({"alias": alias, "upstream_model": target})
            alias, target = m.group(1), None
        m = re.match(r"\s*model:\s*(\S+)", line)
        if m:
            target = m.group(1)
    if alias:
        mapping.append({"alias": alias, "upstream_model": target})
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evaluation/results/baseline50/router_diagnosis.json")
    args = parser.parse_args()

    settings = QASettings.load()
    prompt_template = load_prompt("router.md")
    client = get_openai_client(settings.llm.env_file,
                               settings.llm.api_key_env, settings.llm.base_url_env)
    model = settings.llm.model_name
    if not model:
        from answer.utils import resolve_model_name
        model = resolve_model_name(settings.llm.model_name_env)

    report = {
        "router_model_name_in_answer_config": model,
        "gateway_model_mapping": model_mapping(),
        "production_router_params": {"temperature": 0.0, "max_tokens": 32, "timeout_s": 10},
        "probes": [],
    }
    for tag, q in QUESTIONS:
        prompt = prompt_template.format(question=q)
        entry = {"tag": tag, "question": q, "ladder": []}
        for mt in MAX_TOKENS_LADDER:
            entry["ladder"].append(probe(client, model, prompt, mt))
        report["probes"].append(entry)
        ok32 = entry["ladder"][0].get("extract_json_ok")
        print(f"[{tag}] {q[:30]}… max32 ok={ok32} "
              f"finish={entry['ladder'][0].get('finish_reason')} "
              f"| 256 ok={entry['ladder'][1].get('extract_json_ok')} "
              f"| 1024 ok={entry['ladder'][2].get('extract_json_ok')}")

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nfull diagnosis -> {out_path}")


if __name__ == "__main__":
    main()
