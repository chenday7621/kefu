"""Build the gold mapping (question -> gold docs / chunks / images) for the baseline eval.

Channels and thresholds (chosen from the score distributions produced by
check_mapping.py / check_c2_lang.py; rationale in evaluation/VALIDATION_REPORT.md):

  C2   en string-path refs ("path.md:lines"): extract the manual's own text at
       the labeled lines and score every chunk of that doc with a bidirectional
       containment score; gold if >= 0.8. Forward direction covers "evidence
       inside one chunk"; reverse covers "evidence span crosses chunk
       boundaries". Reverse requires the chunk to have >= 15 ngrams so tiny
       boilerplate chunks cannot ride in. (88.6% of these refs score 1.0 —
       the channel is verbatim by construction, so <0.8 means version drift
       or wrong lines and is recorded as unmapped, not loosened.)
  C1t  dict refs with verbatim `text` (zh): forward overlap >= 0.6.
       (Bimodal distribution; manually sampled bands 0.5-1.0 were all correct,
       0.4 band contained confirmed wrong-chunk matches -> 0.6 keeps margin.)
  C1p  dict refs with paraphrased `summary`/`note`: forward overlap >= 0.8.
       (Paraphrase depresses char overlap; 0.3-0.5 region showed confirmed
       mis-matches and frequent ties -> only quasi-quotes qualify.)

zh line numbers are known-inaccurate (check_mapping Part B: 244 off vs 26
accurate), so lines are never used for zh; zh has no string-path refs anyway.
Refs below threshold / unparseable / cross-lingual land in `unmapped_refs`
with their best score — recorded, never guessed.

Outputs (deterministic given inputs):
  evaluation/gold/gold.jsonl              one record per question
  evaluation/gold/gold_build_config.json  thresholds, coverage, sha256

Usage: python3 evaluation/scripts/build_gold.py
"""
from __future__ import annotations

import csv
import glob
import hashlib
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_mapping", Path(__file__).with_name("check_mapping.py"))
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

ROOT = cm.ROOT
AR = cm.AR
OUT_DIR = ROOT / "evaluation" / "gold"

THRESHOLDS = {"C2": 0.8, "C1t": 0.6, "C1p": 0.8}
MIN_CHUNK_NGRAMS_FOR_REVERSE = 15
NGRAM_N = 3


def load_chunk_index():
    by_doc: dict[str, list[dict]] = {}
    img2chunks: dict[str, list[str]] = {}
    for fp in sorted((ROOT / "process/artifacts/manuals").glob("*/small_chunks.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                by_doc.setdefault(d["doc_name"], []).append({
                    "chunk_id": d["chunk_id"],
                    "ngrams": cm.char_ngrams(d.get("content", "")),
                })
                for p in d.get("image_paths", []):
                    img2chunks.setdefault(Path(p).stem, []).append(d["chunk_id"])
    return by_doc, img2chunks


def make_doc_lookup(by_doc):
    normed = {cm.norm(dn): dn for dn in by_doc}

    def lookup(fname: str):
        stem = fname[:-3] if fname.endswith(".md") else fname
        if stem in by_doc:
            return stem
        alt = stem.replace(" ", "_")
        if alt in by_doc:
            return alt
        return normed.get(cm.norm(stem))
    return lookup


def clean_ref_file(r: dict) -> dict:
    """Some refs embed the line spec in the file field ('x.md:778')."""
    m = re.match(r"^(.+\.md):([\d,\-– ]+)$", r["file"])
    if m:
        r = dict(r)
        r["file"] = m.group(1)
        r["lines"] = r["lines"] or m.group(2)
    return r


def main():
    by_doc, img2chunks = load_chunk_index()
    doc_lookup = make_doc_lookup(by_doc)

    lang, question_text = {}, {}
    for csv_name, lg in (("ch-question.csv", "zh"), ("en-question.csv", "en")):
        with open(AR / csv_name, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                qid = str(row["id"]).strip()
                lang[qid] = lg
                question_text[qid] = row["clean"].strip()

    label_files = {Path(f).stem: f
                   for f in glob.glob(str(AR / "answers/*/per_question/*.json"))}

    man_cache: dict = {}
    stats = Counter()
    records = []

    for qid in sorted(label_files, key=int):
        d = json.load(open(label_files[qid], encoding="utf-8"))
        gold_docs: list[str] = []
        gold_chunks: dict[str, dict] = {}
        unmapped_refs: list[dict] = []

        for idx, raw in enumerate(d.get("evidence_refs", [])):
            r = cm.normalize_ref(raw)
            if not r:
                continue
            r = clean_ref_file(r)
            if not cm.is_substantive(r):
                if r["format"] == "string-free":
                    unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                          "reason": "no_file", "best_score": None})
                    stats["ref_no_file"] += 1
                continue

            dn = doc_lookup(Path(r["file"]).name)
            if dn is None:
                unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                      "reason": "doc_not_found",
                                      "file": r["file"], "best_score": None})
                stats["ref_doc_not_found"] += 1
                continue
            if dn not in gold_docs:
                gold_docs.append(dn)

            # channel selection
            if r["format"] == "string-path" or (not r["text"] and r["lines"]):
                if lang.get(qid) == "zh":
                    # zh line numbers verified inaccurate -> never line-extract
                    unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                          "reason": "zh_lines_untrusted",
                                          "best_score": None})
                    stats["ref_zh_lines_skipped"] += 1
                    continue
                spans = cm.parse_lines_spec(r["lines"])
                lines = cm.read_manual_lines(man_cache, r["file"])
                if not spans or lines is None:
                    unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                          "reason": "lines_unreadable",
                                          "file": r["file"], "best_score": None})
                    stats["ref_lines_unreadable"] += 1
                    continue
                match_text = "\n".join(
                    "\n".join(lines[max(0, lo - 1):hi]) for lo, hi in spans)
                channel = "C2"
            elif r["format"] == "text":
                match_text, channel = r["text"], "C1t"
            elif r["text"]:
                match_text, channel = r["text"], "C1p"
            else:
                unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                      "reason": "no_text_no_lines", "best_score": None})
                stats["ref_no_text_no_lines"] += 1
                continue

            ng = cm.char_ngrams(match_text)
            if not ng:
                unmapped_refs.append({"ref_idx": idx, "format": r["format"],
                                      "reason": "empty_text", "best_score": None})
                continue
            thr = THRESHOLDS[channel]
            scored = []
            for c in by_doc[dn]:
                fwd = len(ng & c["ngrams"]) / len(ng)
                score = fwd
                if channel == "C2" and len(c["ngrams"]) >= MIN_CHUNK_NGRAMS_FOR_REVERSE:
                    score = max(fwd, len(ng & c["ngrams"]) / len(c["ngrams"]))
                scored.append((score, c["chunk_id"]))

            passed = [(s, cid) for s, cid in scored if s >= thr]
            if passed:
                stats[f"ref_mapped_{channel}"] += 1
                for s, cid in passed:
                    prev = gold_chunks.get(cid)
                    if prev is None or s > prev["score"]:
                        gold_chunks[cid] = {"chunk_id": cid, "score": round(s, 4),
                                            "channel": channel, "ref_idx": idx}
            else:
                best_s, best_c = max(scored) if scored else (0.0, "")
                stats[f"ref_below_thr_{channel}"] += 1
                unmapped_refs.append({
                    "ref_idx": idx, "format": r["format"], "channel": channel,
                    "reason": "below_threshold",
                    "best_score": round(best_s, 4), "best_chunk": best_c,
                })

        gold_images = [i for i in d.get("images", []) if isinstance(i, str)]
        image_chunks = sorted({cid for i in gold_images for cid in img2chunks.get(i, [])})

        chunk_list = sorted(gold_chunks.values(),
                            key=lambda x: (-x["score"], x["chunk_id"]))
        rec = {
            "id": qid,
            "lang": lang.get(qid, "?"),
            "question": question_text.get(qid, d.get("question", "")),
            "gold_answer": d.get("content", ""),
            "gold_docs": gold_docs,
            "gold_chunks": chunk_list,
            "gold_chunk_ids": [c["chunk_id"] for c in chunk_list],
            "gold_images": gold_images,
            "gold_image_chunk_ids": image_chunks,
            "unmapped_refs": unmapped_refs,
            "coverage": {
                "chunk": bool(chunk_list),
                "doc": bool(gold_docs),
                "image": bool(gold_images),
            },
        }
        records.append(rec)
        for k in ("chunk", "doc", "image"):
            if rec["coverage"][k]:
                stats[f"q_covered_{k}"] += 1
        if not (rec["coverage"]["chunk"] or rec["coverage"]["image"]):
            stats["q_uncovered_chunk_and_image"] += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gold_path = OUT_DIR / "gold.jsonl"
    with open(gold_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    sha = hashlib.sha256(gold_path.read_bytes()).hexdigest()

    per_lang = Counter()
    for rec in records:
        for k in ("chunk", "doc", "image"):
            if rec["coverage"][k]:
                per_lang[f"{rec['lang']}_{k}"] += 1

    config = {
        "thresholds": THRESHOLDS,
        "ngram_n": NGRAM_N,
        "min_chunk_ngrams_for_reverse": MIN_CHUNK_NGRAMS_FOR_REVERSE,
        "normalization": "strip whitespace/punct, lowercase (check_mapping.norm)",
        "zh_lines_policy": "never line-extract for zh (line numbers verified inaccurate)",
        "questions": len(records),
        "coverage": {
            "chunk": stats["q_covered_chunk"],
            "doc": stats["q_covered_doc"],
            "image": stats["q_covered_image"],
            "neither_chunk_nor_image": stats["q_uncovered_chunk_and_image"],
            "per_lang": dict(sorted(per_lang.items())),
        },
        "ref_stats": {k: v for k, v in sorted(stats.items()) if k.startswith("ref_")},
        "gold_jsonl_sha256": sha,
    }
    with open(OUT_DIR / "gold_build_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(json.dumps(config, ensure_ascii=False, indent=2))
    print(f"\ngold -> {gold_path}")


if __name__ == "__main__":
    main()
