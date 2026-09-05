#!/usr/bin/env python3
"""Filter QA-derived KG inputs to the frozen Train split and audit leakage."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_v1_common import ROOT, load_jsonl, sha256_file, write_json  # noqa: E402


def ids_for(split: str) -> set[str]:
    return {str(row["id"]) for row in load_jsonl(ROOT / "evaluation" / "splits" / "v1" / f"{split}.jsonl")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapped", required=True, help="fresh evidence_mapped.json rebuilt from governed sources")
    parser.add_argument("--semantic", default="kg/state/semantic_edges.json")
    parser.add_argument("--out-dir", default="kg/state/v1_train_only")
    args = parser.parse_args()
    mapped_path, semantic_path, out = ROOT / args.mapped, ROOT / args.semantic, ROOT / args.out_dir
    prior_manifest_path = out / "build_manifest.json"
    prior = json.loads(prior_manifest_path.read_text(encoding="utf-8")) if prior_manifest_path.exists() else {}
    train, dev, heldout = ids_for("train"), ids_for("dev"), ids_for("heldout")
    mapped = json.loads(mapped_path.read_text(encoding="utf-8"))
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    mapped_records = [row for row in mapped.get("records", []) if str(row.get("answer_id")) in train]
    semantic_edges = [row for row in semantic.get("edges", []) if str(row.get("answer_id")) in train]
    out.mkdir(parents=True, exist_ok=True)
    mapped_out = out / "evidence_mapped.json"
    semantic_out = out / "semantic_edges.json"
    write_json(mapped_out, {
        "split_source": "train",
        "stats": {
            "total_records": len(mapped_records),
            "mapped": sum(bool(row.get("chunk_ids")) for row in mapped_records),
            "unmapped": sum(not row.get("chunk_ids") for row in mapped_records),
            "answer_ids": len({str(row.get("answer_id")) for row in mapped_records}),
        },
        "records": mapped_records,
    })
    write_json(semantic_out, {"split_source": "train", "edges": semantic_edges})
    output_ids = {str(row.get("answer_id")) for row in mapped_records} | {str(row.get("answer_id")) for row in semantic_edges}
    dev_overlap, heldout_overlap = sorted(output_ids & dev), sorted(output_ids & heldout)
    split_manifest = json.loads((ROOT / "evaluation" / "splits" / "v1" / "split_manifest.json").read_text(encoding="utf-8"))
    governance = json.loads((ROOT / "evaluation" / "audits" / "dataset_governance_v1.json").read_text(encoding="utf-8"))
    source_mapped_hash = sha256_file(mapped_path)
    source_semantic_hash = sha256_file(semantic_path)
    same_inputs = (
        prior.get("source_dataset_hash") == governance["dataset_hash"]
        and prior.get("split_hash") == split_manifest["split_hash"]
        and prior.get("source_mapped_hash") == source_mapped_hash
        and prior.get("source_semantic_hash") == source_semantic_hash
    )
    manifest = {
        "schema_version": "kg-train-only-v1",
        "split_source": "train-only",
        "build_timestamp": prior.get("build_timestamp") if same_inputs else datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dataset_hash": governance["dataset_hash"],
        "split_hash": split_manifest["split_hash"],
        "source_mapped_hash": source_mapped_hash,
        "source_semantic_hash": source_semantic_hash,
        "mapped_output_hash": sha256_file(mapped_out),
        "semantic_output_hash": sha256_file(semantic_out),
        "mapped_records": len(mapped_records),
        "semantic_edges": len(semantic_edges),
        "source_answer_ids": len(output_ids),
        "dev_answer_id_overlap": dev_overlap,
        "heldout_answer_id_overlap": heldout_overlap,
        "leakage_status": "pass" if not dev_overlap and not heldout_overlap else "fail",
        "official_baseline_v1_runtime_policy": "KG disabled until the train-only graph path is wired and runtime-audited",
    }
    write_json(out / "build_manifest.json", manifest)
    audit_out = ROOT / "evaluation" / "audits" / "kg_leakage_audit_v1.json"
    write_json(audit_out, manifest)
    md = f"""# KG Leakage Audit V1

- QA-derived source: **Train only**
- Mapped evidence records: {len(mapped_records)}
- Retained semantic edges: {len(semantic_edges)}
- Dev answer-ID overlap: {len(dev_overlap)}
- Heldout answer-ID overlap: {len(heldout_overlap)}
- Input leakage audit: **{manifest['leakage_status'].upper()}**
- Official Baseline V1 policy: **KG disabled** until the new graph path is
  explicitly selected by runtime configuration and an end-to-end trace confirms
  that no legacy graph database is opened.

Filtering `CO_EVIDENCE` inputs is insufficient by itself; this script also filters
the QA-derived `SEMANTIC` edges by `answer_id`. The frozen split uses connected
manual components, so no atomic manual is shared across Train, Dev, or Heldout.
"""
    audit_out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["leakage_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
