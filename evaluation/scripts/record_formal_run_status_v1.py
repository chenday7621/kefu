#!/usr/bin/env python3
"""Record why formal V1 runs were or were not allowed to start."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    probe_path = ROOT / "evaluation/results/baseline_v1/preflight/gateway_probe.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    ready = probe.get("gateway_liveliness") == "pass" and probe.get("completion") == "pass"
    for split in ("dev", "heldout"):
        out = ROOT / f"evaluation/results/baseline_v1/{split}/run_status.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "schema_version": "formal-run-status-v1",
            "split": split,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "READY_TO_RUN" if ready else "NOT_RUN_PRECONDITION_FAILED",
            "metrics_available": False,
            "raw_results_available": False,
            "preflight": "evaluation/results/baseline_v1/preflight/gateway_probe.json",
            "reason": None if ready else "frozen answer-model completion preflight failed; see gateway and network preflight artifacts",
            "no_phase1_substitution": True,
        }
        out.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
