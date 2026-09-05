"""Generate BASELINE_350_REPORT.md and pending-audit lists from a finished run.

Reads <dir>/metrics.json, <dir>/raw.jsonl and evaluation/gold/gold.jsonl.
Writes:
  - evaluation/BASELINE_350_REPORT.md
  - evaluation/audits/BASELINE_350_pending_audits.md  (zh hit@1=0, zh hit@5=0,
    fixed-seed random zh/en samples; gold untouched)

Report caveats are hard-coded by design: Hit@1 semantics were manually audited
on the 12-question zh subset (see evaluation/audits/zh_hit1_full12_audit.md);
Hit@5 / MRR / Recall may be UNDERestimated due to gold under-coverage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_SEED = 20260716
N_RANDOM_PER_LANG = 5


def fmt(v, digits=2):
    return "—" if v is None else f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def metric_row(md: dict, key: str) -> str:
    cell = md.get(key) or {}
    return f"{fmt(cell.get('mean'))} (n={cell.get('n', 0)})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="evaluation/results/baseline350")
    args = parser.parse_args()
    rdir = ROOT / args.dir

    metrics = json.load(open(rdir / "metrics.json", encoding="utf-8"))
    raws = [json.loads(l) for l in open(rdir / "raw.jsonl", encoding="utf-8")]
    per_question = metrics["per_question"]
    per_q = {e["id"]: e for e in per_question}
    raw_by_id = {r["id"]: r for r in raws}
    metrics = metrics.get("summary", metrics)  # --out wraps summary; stdout is flat
    metrics["per_question"] = per_question

    c = metrics["counts"]
    rt = metrics["runtime"]
    ro = metrics.get("router") or {}
    date = dt.date.today().isoformat()

    # ---- error / retry bookkeeping ----
    errors = [r for r in raws if r.get("error")]
    n_err = len(errors)

    # ---- audit lists (read-only; gold untouched) ----
    zh_chunk = [e for e in metrics["per_question"]
                if e["lang"] == "zh" and "error" not in e and e.get("hit@1") is not None]
    zh_hit1_0 = sorted((e["id"] for e in zh_chunk if e.get("hit@1") == 0.0), key=int)
    zh_hit5_0 = sorted((e["id"] for e in zh_chunk if e.get("hit@5") == 0.0), key=int)

    ok_ids = {"zh": [], "en": []}
    for e in metrics["per_question"]:
        if "error" not in e and e["lang"] in ok_ids:
            ok_ids[e["lang"]].append(e["id"])
    rng = random.Random(AUDIT_SEED)
    rand_sample = {lg: sorted(rng.sample(ids, min(N_RANDOM_PER_LANG, len(ids))), key=int)
                   for lg, ids in ok_ids.items()}

    audits_dir = ROOT / "evaluation" / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audits_dir / "BASELINE_350_pending_audits.md"

    def qline(qid: str) -> str:
        e = per_q.get(qid, {})
        r = raw_by_id.get(qid, {})
        docs = "、".join(e.get("gold_docs", [])[:2]) if e.get("gold_docs") else "—"
        fr = e.get("first_rank")
        return (f"| {qid} | {r.get('question', '')[:36]} | {docs} | "
                f"{fmt(e.get('hit@1'), 0)} | {fmt(e.get('hit@5'), 0)} | {fr if fr else '>20'} |")

    header = "| id | 问题 | gold 手册 | Hit@1 | Hit@5 | first_rank |\n|---|---|---|---|---|---|"
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(f"# BASELINE_350 待人工审计清单\n\n> 生成于 {date}，随机种子 {AUDIT_SEED}。"
                f"本清单只读生成，未修改 Gold/结果。审计方法沿用 "
                f"`zh_hit1_full12_audit.md`（Top1 语义复核 + Gold 欠覆盖分类）。\n\n")
        f.write(f"## A. 中文 Hit@1 = 0（chunk 可评，共 {len(zh_hit1_0)} 题）\n\n{header}\n")
        f.write("\n".join(qline(q) for q in zh_hit1_0) or "（无）")
        f.write(f"\n\n## B. 中文 Hit@5 = 0（共 {len(zh_hit5_0)} 题，A 的子集优先审）\n\n{header}\n")
        f.write("\n".join(qline(q) for q in zh_hit5_0) or "（无）")
        f.write("\n\n## C. 随机抽样复核（种子固定，可复现）\n")
        for lg in ("zh", "en"):
            f.write(f"\n### {lg}（{len(rand_sample[lg])} 题）\n\n{header}\n")
            f.write("\n".join(qline(q) for q in rand_sample[lg]))
        f.write("\n")

    # ---- report ----
    ret = metrics["retrieval_chunk_gold"]
    img = metrics["retrieval_image_chunks"]
    doc = metrics["doc_routing"]
    ans = metrics["answers"]
    pl = metrics["per_lang"]

    lines = [
        "# InterX Original Baseline — 350 题全量评测报告",
        "",
        f"> 日期：{date} ｜ 结果目录：`{args.dir}/` ｜ git `9679bd2`（tag `phase1-baseline`）",
        "> 配置：原始 InterX（temperature=0.1，Router/检索/回答逻辑未修改），"
        "gold sha256 `d46212…111c`，前 50 题复用 baseline50（配置逐项核对一致）",
        "",
        "## 0. 指标可信度声明",
        "",
        "- **Hit@1 语义已人工审计验证**：中文 12 题全量逐题复核（`evaluation/audits/zh_hit1_full12_audit.md`），"
        "程序 Hit@1 与人工语义判断 100% 一致，无 Gold 错配导致的假阴性。",
        "- **Hit@5、MRR、Recall 可能因 Gold 欠覆盖而系统性偏低**：同一审计发现 12 题中 3 题"
        "（25%）存在 Gold 欠覆盖（正确证据 chunk 未进 gold 集）。这些指标是保守下界，不作横向对比结论的唯一依据。",
        "- 指标只在 Gold 覆盖题上计算，n 逐项标注；覆盖率见 §1。",
        "",
        "## 1. 执行与覆盖",
        "",
        f"| 项 | 值 |\n|---|---|",
        f"| 总题数（350 口径见 VALIDATION_REPORT §1） | {c['total_run']} |",
        f"| 成功 | {c['ok']} |",
        f"| 失败（含 error 记录，可单独重试） | {c['errors']} |",
        f"| Router 判为 general（跳过检索） | {c['routed_general']} |",
        f"| chunk Gold 可评题 | {c['chunk_eligible']} |",
        f"| 图片 Gold 可评题 | {c['imgchunk_eligible']} |",
        f"| doc Gold 可评题 | {c['doc_eligible']} |",
        "",
        "## 2. 检索指标（Strict chunk Gold）",
        "",
        "| 指标 | 总体 | zh | en |",
        "|---|---|---|---|",
    ]
    for k in ("hit@1", "hit@3", "hit@5", "mrr", "recall@1", "recall@3", "recall@5"):
        lines.append(f"| {k} | {metric_row(ret, k)} | "
                     f"{metric_row(pl.get('zh', {}), k)} | {metric_row(pl.get('en', {}), k)} |")
    lines += [
        "",
        "## 3. 辅助通道",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| doc hit@1 | {metric_row(doc, 'doc_hit@1')} |",
        f"| doc hit@5 | {metric_row(doc, 'doc_hit@5')} |",
        f"| 图片-chunk hit@5（阈值无关交叉验证） | {metric_row(img, 'imgchunk_hit@5')} |",
        f"| 图片-chunk MRR | {metric_row(img, 'imgchunk_mrr')} |",
        "",
        "## 4. 答案图片指标",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 图片 recall | {metric_row(ans, 'image_recall')} |",
        f"| 图片 precision | {metric_row(ans, 'image_precision')} |",
        f"| 图片完全一致率 | {metric_row(ans, 'image_exact_match')} |",
        f"| `<PIC>` 一致性 | {metric_row(ans, 'pic_placeholder_consistent')} |",
        f"| 平均答案长度 | {metric_row(ans, 'answer_len')} |",
        "",
        "## 5. 延迟",
        "",
        f"| p50 | p95 | mean |\n|---|---|---|\n"
        f"| {fmt(rt.get('p50_s'), 1)}s | {fmt(rt.get('p95_s'), 1)}s | {fmt(rt.get('mean_s'), 1)}s |",
        "",
        "## 6. Router（插桩观测，未修改）",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 调用 | {ro.get('calls', '—')} |",
        f"| 失败（全部为空返回，根因见 router_diagnosis.json：max_tokens=32 + 推理模型） | {ro.get('failed', '—')} |",
        f"| 失败但 fallback RAG 成功（非降级失败） | {ro.get('failed_but_fallback_rag_ok', '—')} |",
        f"| 判为 general | {ro.get('routed_general', '—')} |",
        f"| Router 耗时 p50/p95 | {fmt(ro.get('elapsed_p50_s'))}s / {fmt(ro.get('elapsed_p95_s'))}s |",
        "",
        "## 7. 错误与重试",
        "",
        (f"{n_err} 题失败，error/traceback 已保存于 raw.jsonl，"
         f"重试命令见 README（--retry-errors）。失败题清单："
         + "、".join(r["id"] for r in errors[:30])) if n_err else "无失败题。",
        "",
        "## 8. 待人工审计清单",
        "",
        f"见 `evaluation/audits/BASELINE_350_pending_audits.md`（中文 Hit@1=0 共 {len(zh_hit1_0)} 题、"
        f"中文 Hit@5=0 共 {len(zh_hit5_0)} 题、随机 zh/en 各 {N_RANDOM_PER_LANG} 题，种子 {AUDIT_SEED}）。"
        "审计只读，Gold 未修改。",
        "",
    ]
    report_path = ROOT / "evaluation" / "BASELINE_350_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {report_path}")
    print(f"audit lists -> {audit_path}")


if __name__ == "__main__":
    main()
