#!/usr/bin/env python3
"""Check local secret files without reading or printing their contents."""
from __future__ import annotations

import json
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    rows = []
    for path in sorted(ROOT.glob("*/.env")):
        mode = stat.S_IMODE(path.stat().st_mode)
        rows.append({
            "path": path.relative_to(ROOT).as_posix(),
            "mode": oct(mode),
            "secure": mode & 0o077 == 0,
        })
    status = "pass" if rows and all(row["secure"] for row in rows) else "pass_no_local_secrets" if not rows else "fail"
    report = {"schema_version": "secret-permission-audit-v1", "status": status, "files": rows}
    out = ROOT / "evaluation" / "audits" / "secret_permissions_v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if status.startswith("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
