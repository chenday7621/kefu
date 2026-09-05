"""Feasibility audit for the phase-1 baseline evaluation. Read-only analysis.

Part A — dataset audit: question counts, id uniqueness, label coverage,
evidence_refs format census (5 observed formats), per-question mappability.

Part B — line-number accuracy: for refs having BOTH text and lines, compare
the ref text against the labeled line range of the current agentic-rag manual.
High overlap = line numbers trustworthy; low = stale/offset.

Part C — evidence->chunk overlap distributions, split by evidence source:
  C1. refs with text/summary: match label text to chunks (paraphrase-limited)
  C2. bare-string / no-text refs with lines: extract the manual's own text at
      the labeled lines, match THAT to chunks (verbatim path — should be high
      iff line numbers and manual version align)
No threshold is assumed; distributions inform the choice afterwards.

Writes evaluation/gold/match_samples.json (per-band samples for review).
"""
from __future__ import annotations

import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AR = ROOT / "agentic-rag"
MANUALS_DIR = ROOT / "process" / "artifacts" / "manuals"
OUT_DIR = ROOT / "evaluation" / "gold"

OVERVIEW_NAMES = {"手册内容总览.md"}
STRING_REF_RE = re.compile(r"^(?P<path>[^:]+\.md):(?P<lines>[\d,\-– ]+)$")
LINES_RE = re.compile(r"^(\d+)(?:\s*[-–]\s*(\d+))?$")


def norm(s: str) -> str:
    return re.sub(r"[\s，。：；、（）()【】\[\]!！?？·\-—~～\"'“”‘’,.:;<>《》*#|]+", "", s).lower()


def char_ngrams(s: str, n: int = 3) -> set:
    s = norm(s)
    return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else ({s} if s else set())


def parse_lines_spec(spec: str) -> list[tuple[int, int]]:
    """Parse '290-292' / '7,9' / '2051' into [(lo, hi), ...]."""
    spans = []
    for part in str(spec).split(","):
        m = LINES_RE.match(part.strip())
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2) or m.group(1))
            spans.append((lo, hi))
    return spans


def normalize_ref(ref):
    """Normalize the 5 observed evidence_refs formats to one dict.

    A. dict file+text      -> verbatim-ish excerpt
    B. dict file+summary   -> paraphrase
    C. dict source+summary -> paraphrase (key rename)
    D. dict file+note      -> paraphrase (key rename)
    E. "path.md:lines" str -> lines only, no label text
    """
    if isinstance(ref, str):
        m = STRING_REF_RE.match(ref.strip())
        if m:
            return {"file": m.group("path"), "lines": m.group("lines"),
                    "text": "", "format": "string-path"}
        return {"file": "", "lines": "", "text": ref, "format": "string-free"}
    if isinstance(ref, dict):
        file = str(ref.get("file") or ref.get("source") or "")
        text = str(ref.get("text") or "")
        para = str(ref.get("summary") or ref.get("note") or "")
        if text:
            fmt = "text"
        elif para:
            fmt = "summary" if ref.get("summary") else "note"
        else:
            fmt = "dict-other"
        return {"file": file, "lines": str(ref.get("lines", "")),
                "text": text or para, "format": fmt}
    return None


def is_substantive(r: dict) -> bool:
    return bool(r and r["file"] and Path(r["file"]).name not in OVERVIEW_NAMES)


def read_manual_lines(cache: dict, rel_path: str) -> list[str] | None:
    if rel_path not in cache:
        p = ROOT / rel_path
        if not rel_path.endswith(".md") or not p.exists():
            cache[rel_path] = None
        else:
            try:
                cache[rel_path] = p.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                cache[rel_path] = None
    return cache[rel_path]


def main():
    # ---------- Part A ----------
    print("=" * 62)
    print("PART A — dataset audit")
    print("=" * 62)
    qs: dict[str, dict] = {}
    for csv_name, lang in (("ch-question.csv", "zh"), ("en-question.csv", "en")):
        with open(AR / csv_name, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                qid = str(r["id"]).strip()
                if qid in qs:
                    print(f"  !! duplicate id across CSVs: {qid}")
                qs[qid] = {"lang": lang}
    n_zh = sum(1 for q in qs.values() if q["lang"] == "zh")
    print(f"questions: zh={n_zh} en={len(qs) - n_zh} total={len(qs)} unique_ids={len(qs)}")

    label_files = {Path(f).stem: f
                   for f in glob.glob(str(AR / "answers" / "*" / "per_question" / "*.json"))}
    print(f"label files: {len(label_files)}; "
          f"missing={sorted(set(qs) - set(label_files), key=int) or 'none'}; "
          f"extra={sorted(set(label_files) - set(qs), key=int) or 'none'}")

    fmt_counter = Counter()
    q_mappable = Counter()
    q_no_map = []
    gold_img_q = 0
    for qid, qf in sorted(label_files.items(), key=lambda kv: int(kv[0])):
        d = json.load(open(qf, encoding="utf-8"))
        refs = [normalize_ref(r) for r in d.get("evidence_refs", [])]
        refs = [r for r in refs if r]
        for r in refs:
            fmt_counter[r["format"]] += 1
        subst = [r for r in refs if is_substantive(r)]
        has_text = any(r["text"] for r in subst)
        has_lines = any(parse_lines_spec(r["lines"]) for r in subst)
        if d.get("images"):
            gold_img_q += 1
        if subst:
            q_mappable["has_substantive_ref"] += 1
            if has_text:
                q_mappable["ref_with_text"] += 1
            if has_lines:
                q_mappable["ref_with_lines"] += 1
        else:
            q_no_map.append(qid)
    print(f"ref format census: {dict(fmt_counter)}")
    print(f"questions with substantive ref: {q_mappable['has_substantive_ref']}/350 "
          f"(with text: {q_mappable['ref_with_text']}, with parseable lines: {q_mappable['ref_with_lines']})")
    print(f"questions with NO substantive ref: {len(q_no_map)} -> {q_no_map[:25]}")
    print(f"questions with >=1 gold image: {gold_img_q}/350")

    # ---------- chunks ----------
    by_doc: dict[str, list[dict]] = {}
    img2exists = set()
    for fp in sorted(MANUALS_DIR.glob("*/small_chunks.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                by_doc.setdefault(d["doc_name"], []).append({
                    "chunk_id": d["chunk_id"],
                    "ngrams": char_ngrams(d.get("content", "")),
                    "content": d.get("content", ""),
                })
                for p in d.get("image_paths", []):
                    img2exists.add(Path(p).stem)
    n_chunks = sum(len(v) for v in by_doc.values())

    # map evidence file stem -> chunk doc_name (en manuals use spaces vs underscores)
    def doc_lookup(fname: str):
        stem = fname[:-3] if fname.endswith(".md") else fname
        if stem in by_doc:
            return stem
        alt = stem.replace(" ", "_")
        if alt in by_doc:
            return alt
        for dn in by_doc:
            if norm(dn) == norm(stem):
                return dn
        return None

    # ---------- Part B: line accuracy ----------
    print()
    print("=" * 62)
    print("PART B — line-number accuracy (refs with BOTH text and lines)")
    print("=" * 62)
    man_cache: dict = {}
    line_acc = {"zh": Counter(), "en": Counter()}
    for qid, qf in sorted(label_files.items(), key=lambda kv: int(kv[0])):
        d = json.load(open(qf, encoding="utf-8"))
        lang = qs.get(qid, {}).get("lang", "?")
        for raw in d.get("evidence_refs", []):
            r = normalize_ref(raw)
            if not (is_substantive(r) and r["text"] and parse_lines_spec(r["lines"])):
                continue
            lines = read_manual_lines(man_cache, r["file"])
            if lines is None:
                line_acc[lang]["manual_missing"] += 1
                continue
            seg = "".join(
                "".join(lines[max(0, lo - 1):hi]) for lo, hi in parse_lines_spec(r["lines"])
            )
            ng = char_ngrams(r["text"])
            ov = len(ng & char_ngrams(seg)) / max(1, len(ng))
            if ov >= 0.5:
                line_acc[lang]["accurate(>=0.5)"] += 1
            elif ov >= 0.2:
                line_acc[lang]["partial(0.2-0.5)"] += 1
            else:
                line_acc[lang]["off(<0.2)"] += 1
    for lang in ("zh", "en"):
        print(f"  {lang}: {dict(line_acc[lang]) or '(no refs with text+lines)'}")

    # ---------- Part C: evidence->chunk distributions ----------
    print()
    print("=" * 62)
    print(f"PART C — evidence->chunk overlap ({n_chunks} chunks, {len(by_doc)} docs)")
    print("=" * 62)

    hists = {"C1-labeltext": Counter(), "C2-manuallines": Counter()}
    fmt_band = Counter()
    tie_stats = Counter()
    doc_unmapped = Counter()
    samples: dict[str, list] = {}
    lowlights = []

    for qid, qf in sorted(label_files.items(), key=lambda kv: int(kv[0])):
        d = json.load(open(qf, encoding="utf-8"))
        for raw in d.get("evidence_refs", []):
            r = normalize_ref(raw)
            if not is_substantive(r):
                continue
            dn = doc_lookup(Path(r["file"]).name)
            if dn is None:
                doc_unmapped[Path(r["file"]).name] += 1
                continue

            # choose match text: C1 label text; C2 manual's own lines
            if r["text"]:
                channel, match_text = "C1-labeltext", r["text"]
            else:
                spans = parse_lines_spec(r["lines"])
                lines = read_manual_lines(man_cache, r["file"]) if spans else None
                if not spans or lines is None:
                    continue
                match_text = "".join(
                    "\n".join(lines[max(0, lo - 1):hi]) for lo, hi in spans
                )
                channel = "C2-manuallines"
            ng = char_ngrams(match_text)
            if not ng:
                hists[channel]["(empty)"] += 1
                continue
            scored = sorted(
                ((len(ng & c["ngrams"]) / len(ng), c["chunk_id"], c["content"])
                 for c in by_doc[dn]),
                reverse=True,
            )
            best, best_cid, best_content = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0.0
            band = f"{min(int(best * 10), 10) / 10:.1f}"
            hists[channel][band] += 1
            fmt_band[(r["format"], band)] += 1
            tie_stats[f"{channel}|tie" if best - second < 0.05 else f"{channel}|clear"] += 1
            if best < 0.35:
                lowlights.append((best, qid, r["format"], dn))
            key = f"{channel}|{band}"
            if len(samples.setdefault(key, [])) < 3:
                samples[key].append({
                    "qid": qid, "doc": dn, "format": r["format"],
                    "best": round(best, 3), "second": round(second, 3),
                    "best_chunk": best_cid,
                    "match_text": match_text[:150], "chunk_content": best_content[:150],
                })

    for ch_name, hist in hists.items():
        total = sum(hist.values())
        print(f"\n{ch_name} histogram (n={total}):")
        for band in sorted(hist, reverse=True):
            bar = "#" * int(hist[band] * 50 / max(1, total))
            print(f"  {band}: {hist[band]:4d} {bar}")
    print(f"\ntie(<0.05 gap) vs clear: {dict(tie_stats)}")
    print("\nformat x band:")
    for fmt in sorted({k[0] for k in fmt_band}):
        row = {b: fmt_band[(fmt, b)] for b in sorted({k[1] for k in fmt_band if k[0] == fmt}, reverse=True)}
        print(f"  {fmt}: {row}")
    if doc_unmapped:
        print(f"\nevidence files not mapped to any chunk doc: {dict(doc_unmapped)}")
    print(f"\nrefs with best<0.35: {len(lowlights)}; worst 10:")
    for b, qid, fmt, dn in sorted(lowlights)[:10]:
        print(f"  {b:.3f} q{qid} [{fmt}] {dn}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sp = OUT_DIR / "match_samples.json"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    print(f"\nper-band samples -> {sp}")


if __name__ == "__main__":
    main()
