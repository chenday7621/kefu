from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for source in ("evaluation/scripts", "answer/src", "retrieval/src", "kg/src", "chat/src", "process/src"):
    path = str(ROOT / source)
    if path not in sys.path:
        sys.path.insert(0, path)
