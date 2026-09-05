#!/usr/bin/env python3
"""Optional live KG-on/KG-off diagnostic; never execute during pytest import.

This historical comparison makes paid model calls and is not part of the
Baseline V1 offline test suite. Run this file explicitly only when a future KG
experiment is authorized. Baseline V1 itself keeps KG disabled.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from answer.config import QASettings
from answer.pipeline import answer


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "kg" / "tests" / "kg_compare_results.json"


def main() -> int:
    """Run the legacy live comparison only after explicit script execution."""
    logging.basicConfig(level=logging.WARNING)
    question = "How do I update the firmware on my camera?"
    results = []

    for kg_on, label in ((True, "KG-ON"), (False, "KG-OFF")):
        settings = QASettings.load()
        object.__setattr__(settings.kg, "enabled", kg_on)
        started = time.monotonic()
        try:
            result = answer(question, settings=settings)
            entry = {
                "label": label,
                "kg": kg_on,
                "time_s": round(time.monotonic() - started, 2),
                "small_hits": result.recall_meta.small_hit_count,
                "kg_expansion": result.recall_meta.kg_expansion_count,
                "mid_hits": result.recall_meta.mid_hit_count,
                "big_hits": result.recall_meta.big_hit_count,
                "answer": result.final_answer.content[:500],
            }
        except Exception as exc:  # pragma: no cover - optional live diagnostic
            entry = {
                "label": label,
                "kg": kg_on,
                "time_s": round(time.monotonic() - started, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(entry)
        OUT.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[{label}] done in {entry['time_s']}s", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
