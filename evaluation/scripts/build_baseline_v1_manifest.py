#!/usr/bin/env python3
"""Build the non-secret, hash-addressed Baseline V1 environment manifest."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, sha256_file, sha256_records, sha256_tree, write_json  # noqa: E402


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def optional_hash(path: Path) -> str | None:
    return sha256_file(path) if path.exists() and path.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evaluation/baselines/baseline_v1_environment_manifest.json")
    args = parser.parse_args()
    split = json.loads((ROOT / "evaluation/splits/v1/split_manifest.json").read_text(encoding="utf-8"))
    governance = json.loads((ROOT / "evaluation/audits/dataset_governance_v1.json").read_text(encoding="utf-8"))
    gold = json.loads((ROOT / "evaluation/gold_v2/manifest.json").read_text(encoding="utf-8"))
    kg = json.loads((ROOT / "kg/state/v1_train_only/build_manifest.json").read_text(encoding="utf-8"))
    protocol_path = ROOT / "evaluation/configs/baseline_v1.yaml"
    answer_path = ROOT / "answer/configs/baseline_v1.yaml"
    retrieval_path = ROOT / "retrieval/configs/default.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    corpus_parts = {
        "manual_artifacts_tree": sha256_tree(ROOT / "process/artifacts/manuals"),
        "milvus_lite_tree": sha256_tree(ROOT / "process/artifacts/manual_chunks.db"),
    }
    manifest = {
        "schema_version": "baseline-v1-environment-manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_name": "InterX-350 Silver Benchmark",
        "git": {
            "head": git("rev-parse", "HEAD"),
            "tags_at_head": git("tag", "--points-at", "HEAD").splitlines(),
            "worktree_clean": not bool(git("status", "--porcelain")),
            "baseline_v1_tag": "baseline-v1" if "baseline-v1" in git("tag", "--list", "baseline-v1").splitlines() else None,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "workers": protocol["execution"]["query_workers"],
            "concurrency": protocol["execution"]["concurrency"],
            "warmup_ids": protocol["execution"]["warmup_ids"],
            "reload_policy": protocol["execution"]["retrieval_reload_policy"],
            "kg_enabled": protocol["kg"]["enabled"],
        },
        "hashes": {
            "dataset": governance["dataset_hash"],
            "split": split["split_hash"],
            "gold_v2": gold["references_hash"],
            "gold_v2_schema": gold["schema_hash"],
            "kg_build_manifest": sha256_file(ROOT / "kg/state/v1_train_only/build_manifest.json"),
            "kg_mapped": kg["mapped_output_hash"],
            "kg_semantic": kg["semantic_output_hash"],
            "baseline_protocol": sha256_file(protocol_path),
            "answer_config": sha256_file(answer_path),
            "retrieval_config": sha256_file(retrieval_path),
            "dependency_lock": sha256_file(ROOT / "requirements-baseline-v1.lock"),
            "corpus_parts": corpus_parts,
            "corpus": sha256_records([corpus_parts]),
        },
        "models": {
            "answer": protocol["answer"]["model_alias"],
            "rewrite": protocol["answer"]["rewrite_model_alias"],
            "embedding": protocol["retrieval"]["embedding_model"],
            "reranker": protocol["retrieval"]["reranker_model"],
            "provider_revision": "unavailable_until_successful_gateway_run",
        },
        "inputs_present": {
            "corpus": (ROOT / "process/artifacts/manuals").is_dir(),
            "vector_db": (ROOT / "process/artifacts/manual_chunks.db").is_dir(),
            "gold_v2": (ROOT / "evaluation/gold_v2/references.jsonl").is_file(),
            "dev_split": (ROOT / "evaluation/splits/v1/dev.jsonl").is_file(),
            "heldout_split": (ROOT / "evaluation/splits/v1/heldout.jsonl").is_file(),
        },
    }
    write_json(ROOT / args.out, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
