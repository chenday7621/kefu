"""Offline verification entry point. Does not execute benchmark tasks."""
from pathlib import Path
import hashlib
import json

def verify(root):
    for line in (root / "results/checksums.sha256").read_text().splitlines():
        expected, name = line.split("  ", 1)
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Unsafe checksum path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    summary = json.loads((root / "results/baseline_v2_summary.json").read_text())
    if summary["success_count"] / summary["task_count"] != summary["task_success_rate"]:
        raise ValueError("Inconsistent aggregate")
    mapping = json.loads((root / "docs/SOURCE_PROVENANCE.json").read_text())
    for item in mapping["public_runtime_files"]:
        if hashlib.sha256((root / item["public_path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Runtime source changed")
    return {"status": "PASS", "scope": "offline public artifacts/source integrity", "task_success_rate": summary["task_success_rate"]}

def main():
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), indent=2))

if __name__ == "__main__":
    main()
