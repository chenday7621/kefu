"""On-demand question decomposition for multi-query recall (phase 2, off = baseline).

A single LLM call both decides whether the question is composite and, if so,
splits it into self-contained sub-questions. Best-effort: any failure returns
[question] so downstream retrieval always has at least one query.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .config import QASettings
from .utils import extract_json, get_openai_client, load_prompt, resolve_model_name

log = logging.getLogger(__name__)


def decompose_question(question: str, *, settings: QASettings, telemetry: Any | None = None) -> list[str]:
    """
    Split a composite question into 2..max_sub_questions self-contained queries.

    Returns [question] when decomposition is disabled, judged unnecessary,
    or anything fails — the degraded path is identical to the baseline.
    """
    config = settings.decompose
    if not config.enabled:
        return [question]

    try:
        client = get_openai_client(
            settings.rewrite_llm.env_file,
            settings.rewrite_llm.api_key_env,
            settings.rewrite_llm.base_url_env,
        )
        model = resolve_model_name(
            settings.rewrite_llm.env_file,
            settings.rewrite_llm.model_name,
            settings.rewrite_llm.model_name_env,
        )
        prompt = load_prompt("decompose.md").format(
            question=question, max_sub_questions=config.max_sub_questions
        )

        call_started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout_seconds,
            )
        except Exception as exc:
            if telemetry:
                telemetry.model_call(stage="decompose", model=model, elapsed_ms=(time.monotonic() - call_started) * 1000, error=exc)
            raise
        if telemetry:
            telemetry.model_call(stage="decompose", model=model, elapsed_ms=(time.monotonic() - call_started) * 1000, response=response)
        raw = (response.choices[0].message.content or "").strip()
        data = extract_json(raw)

        if not data.get("need_decompose"):
            return [question]
        subs = [str(s).strip() for s in (data.get("sub_questions") or []) if str(s).strip()]
        if len(subs) < 2:
            return [question]
        return subs[: config.max_sub_questions]
    except Exception as exc:
        log.warning("Decompose failed, using original question: %s", exc)
        if telemetry:
            telemetry.fallback("decompose_to_original")
        return [question]
