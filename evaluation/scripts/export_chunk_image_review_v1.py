#!/usr/bin/env python3
"""Export human-friendly Candidate chunk/image review worksheets.

This exporter never reads runtime retrieval results and never changes Gold review
decisions. Candidate mappings come from Source Gold line overlap prepared by the
Human Gold Verification infrastructure.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from baseline_v1_common import ROOT, numeric_key
from gold_verification_common import load_chunk_levels, load_review_records


VERIFY_ROOT = ROOT / "evaluation/gold_verification/v1"
LEVELS = ("small", "mid", "big")
REVIEW_FIELDS = ["题号", "题目", "所属产品", "当前chunkid列表", "图片id列表", "是否修改"]


def dumped(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_existing_edits(path: Path) -> dict[str, dict[str, str]]:
    """Keep human edits when a worksheet is regenerated."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("题号", "")): row
            for row in csv.DictReader(handle)
            if str(row.get("是否修改", "")).strip()
        }


def products_for_chunks(
    chunk_ids: list[str],
    chunks_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    products: list[str] = []
    for chunk_id in chunk_ids:
        chunk = chunks_by_id.get(chunk_id) or {}
        product = str(chunk.get("product_name") or chunk.get("doc_name") or "").strip()
        if product and product not in products:
            products.append(product)
    return products


def export_split(split: str, chunks_by_id: dict[str, dict[str, Any]]) -> dict[str, int]:
    source = VERIFY_ROOT / split / f"{split.upper()}_GOLD_REVIEW.csv"
    records = sorted(load_review_records(source), key=lambda row: numeric_key(row["id"]))
    review_rows: list[dict[str, Any]] = []
    prefix = split.upper()
    directory = VERIFY_ROOT / split
    output = directory / f"{prefix}_CHUNK_IMAGE_REVIEW.csv"
    existing_edits = load_existing_edits(output)

    for record in records:
        mapping = record["candidate_chunk_mapping"]
        level_ids = {
            level: list(mapping.get(f"acceptable_{level}_chunk_ids") or [])
            for level in LEVELS
        }
        images = record.get("candidate_gold_images") or []
        all_chunk_ids = level_ids["small"] + level_ids["mid"] + level_ids["big"]
        row = {
            "题号": record["id"],
            "题目": record["question"],
            "所属产品": "；".join(products_for_chunks(all_chunk_ids, chunks_by_id)),
            "当前chunkid列表": dumped(all_chunk_ids),
            "图片id列表": dumped([item["image_id"] for item in images]),
            "是否修改": "",
        }
        old = existing_edits.get(str(record["id"]))
        if old:
            row["当前chunkid列表"] = old.get("当前chunkid列表", row["当前chunkid列表"])
            row["图片id列表"] = old.get("图片id列表", row["图片id列表"])
            row["是否修改"] = old.get("是否修改", "")
        review_rows.append(row)

    write_csv(output, REVIEW_FIELDS, review_rows)
    return {
        "questions": len(review_rows),
        "chunk_ids": sum(len(json.loads(row["当前chunkid列表"])) for row in review_rows),
        "image_ids": sum(len(json.loads(row["图片id列表"])) for row in review_rows),
    }


def main() -> int:
    levels = load_chunk_levels()
    chunks_by_id = {
        str(chunk["chunk_id"]): chunk
        for chunks in levels.values()
        for chunk in chunks
    }
    result = {split: export_split(split, chunks_by_id) for split in ("dev", "heldout")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
