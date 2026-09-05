#!/usr/bin/env python3
"""Run one full hybrid Retrieval request and preserve its stage telemetry."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "retrieval" / "src"))

from retrieval import reload, search_hierarchical  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="空调制冷效果差怎么办")
    parser.add_argument("--out", default="evaluation/results/baseline_v1/preflight/retrieval_probe.json")
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    record = {
        "schema_version": "retrieval-preflight-v1",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "fail",
        "query": args.query,
        "wall_ms": None,
        "small_hits": 0,
        "mid_hits": 0,
        "big_hits": 0,
        "top_chunk_id": None,
        "retrieval_meta": None,
        "error": None,
    }
    try:
        reload()
        result = search_hierarchical(args.query, top_k=5)
        record.update(
            status="pass",
            small_hits=len(result.small_hits),
            mid_hits=len(result.mid_hits),
            big_hits=len(result.big_hits),
            top_chunk_id=result.small_hits[0].chunk_id if result.small_hits else None,
            retrieval_meta=result.meta.to_dict(),
        )
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: retrieval request failed"
    record["wall_ms"] = round((time.monotonic() - started) * 1000, 3)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"retrieval: {record['status']} wall_ms={record['wall_ms']}")
    return 0 if record["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
