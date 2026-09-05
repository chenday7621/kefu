"""Split the C2 channel (string-path refs) by language and list missing manual paths.

Answers three questions before the gold threshold is fixed:
1. how many string-path refs belong to zh vs en questions
2. C2 best-overlap distribution per language (zh line numbers are known-bad,
   so high zh C2 scores would be silently-wrong gold and must be quantified)
3. which manual paths referenced by zh text+lines refs do not exist on disk
"""
from __future__ import annotations

import csv
import glob
import json
from collections import Counter
from pathlib import Path

import importlib.util

spec = importlib.util.spec_from_file_location(
    "check_mapping", Path(__file__).with_name("check_mapping.py"))
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module.__self__ if False else spec.loader.exec_module(cm)  # load helpers

ROOT = cm.ROOT
AR = cm.AR


def main():
    lang = {}
    for csv_name, lg in (("ch-question.csv", "zh"), ("en-question.csv", "en")):
        with open(AR / csv_name, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                lang[str(r["id"]).strip()] = lg

    by_doc = {}
    for fp in sorted((ROOT / "process/artifacts/manuals").glob("*/small_chunks.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                by_doc.setdefault(d["doc_name"], []).append(
                    {"ngrams": cm.char_ngrams(d.get("content", ""))})

    def doc_lookup(fname):
        stem = fname[:-3] if fname.endswith(".md") else fname
        if stem in by_doc:
            return stem
        alt = stem.replace(" ", "_")
        if alt in by_doc:
            return alt
        for dn in by_doc:
            if cm.norm(dn) == cm.norm(stem):
                return dn
        return None

    man_cache = {}
    fmt_lang = Counter()
    c2_hist = {"zh": Counter(), "en": Counter()}
    missing_paths = Counter()

    for qf in glob.glob(str(AR / "answers/*/per_question/*.json")):
        qid = Path(qf).stem
        lg = lang.get(qid, "?")
        d = json.load(open(qf, encoding="utf-8"))
        for raw in d.get("evidence_refs", []):
            r = cm.normalize_ref(raw)
            if not r:
                continue
            fmt_lang[(r["format"], lg)] += 1
            if not cm.is_substantive(r):
                continue
            lines_exist = cm.read_manual_lines(man_cache, r["file"])
            if lines_exist is None and r["file"]:
                missing_paths[r["file"]] += 1
            if r["format"] != "string-path":
                continue
            dn = doc_lookup(Path(r["file"]).name)
            spans = cm.parse_lines_spec(r["lines"])
            if dn is None or not spans or lines_exist is None:
                c2_hist[lg]["(unresolvable)"] += 1
                continue
            text = "".join("\n".join(lines_exist[max(0, lo - 1):hi]) for lo, hi in spans)
            ng = cm.char_ngrams(text)
            if not ng:
                c2_hist[lg]["(empty)"] += 1
                continue
            best = max(len(ng & c["ngrams"]) / len(ng) for c in by_doc[dn])
            c2_hist[lg][f"{min(int(best * 10), 10) / 10:.1f}"] += 1

    print("format x lang:")
    for fmt in sorted({k[0] for k in fmt_lang}):
        print(f"  {fmt}: zh={fmt_lang[(fmt, 'zh')]} en={fmt_lang[(fmt, 'en')]}")
    print("\nC2 (string-path) best-overlap by language:")
    for lg in ("zh", "en"):
        print(f"  {lg}: { {b: c2_hist[lg][b] for b in sorted(c2_hist[lg], reverse=True)} }")
    print(f"\nmissing manual paths ({len(missing_paths)} unique):")
    for p, n in missing_paths.most_common(15):
        print(f"  {n:3d}x {p}")


if __name__ == "__main__":
    main()
