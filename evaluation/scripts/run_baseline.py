"""Phase-1 baseline batch runner.

Calls answer.pipeline.answer() in-process (dependencies initialized once),
iterates over the 351-question benchmark, and writes one JSON line per
question with the full QAResult, the ranked retrieval hits, timing, and
any exception. Supports resume: already-present ids in the output file
are skipped.

The project's answer code is NOT modified. To capture ranked retrieval
hits (rank/score per chunk, which QAResult does not carry), the runner
wraps answer.pipeline.search_hierarchical with a thin capturing proxy.

Concurrency (--workers N, default 1): questions run in a thread pool.
Results are bit-identical to sequential runs; three harness-level guards
make it safe without touching project code:
  - capture proxies store per-thread state (threading.local)
  - KG expansion is serialized behind a lock (kuzu opens the same .kuzu
    path read-write per question; concurrent opens would fail and be
    silently degraded by answer()'s try/except — a behavior change)
  - retrieval_reload becomes load-once/no-op (it only re-reads static
    artifacts; per-question cache drops would race concurrent searches)
Per-question wall_seconds under concurrency includes contention and is
not comparable to sequential latency numbers (flagged via "workers").

Usage:
  chat/.venv/bin/python evaluation/scripts/run_baseline.py \
      --out evaluation/results/baseline/raw.jsonl \
      [--limit 5] [--ids 64,65] [--lang zh] [--retry-errors] [--workers 3]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))

import logging  # noqa: E402

import answer.pipeline as ap  # noqa: E402  (also wires retrieval/kg sys.path)
import answer.router as arouter  # noqa: E402


def load_questions(lang: str | None) -> list[dict]:
    rows: list[dict] = []
    for csv_name, l in (("ch-question.csv", "zh"), ("en-question.csv", "en")):
        if lang and l != lang:
            continue
        with open(ROOT / "agentic-rag" / csv_name, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rows.append({"id": str(r["id"]).strip(), "question": r["clean"].strip(), "lang": l})
    rows.sort(key=lambda r: int(r["id"]))
    return rows


class _RouterLogTap(logging.Handler):
    """Capture 'Router failed' warnings emitted inside route_question.

    Log handlers run synchronously in the emitting thread, so per-thread
    state keeps concurrent questions from clobbering each other.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self._local = threading.local()

    @property
    def last_fail(self) -> str | None:
        return getattr(self._local, "last_fail", None)

    @last_fail.setter
    def last_fail(self, value):
        self._local.last_fail = value

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith("Router failed"):
            self._local.last_fail = msg


class RouterCapture:
    """Wrap answer.pipeline.route_question to time it and classify its outcome.

    route_question swallows its own exceptions and falls back to RAG, so the
    only failure signal is the warning it logs; a log tap on answer.router
    distinguishes 'genuine RAG classification' from 'failed -> RAG fallback'.
    Behavior is unchanged — this is observation only.
    """

    def __init__(self):
        self._orig = ap.route_question
        self._tap = _RouterLogTap()
        arouter.log.addHandler(self._tap)
        self._local = threading.local()

    @property
    def last(self) -> dict | None:
        return getattr(self._local, "last", None)

    @last.setter
    def last(self, value):
        self._local.last = value

    def __call__(self, question, **kwargs):
        self._tap.last_fail = None
        t0 = time.monotonic()
        routed_rag = self._orig(question, **kwargs)
        elapsed = round(time.monotonic() - t0, 3)
        fail = self._tap.last_fail
        empty_return = bool(fail) and "Expecting value: line 1 column 1" in fail
        self._local.last = {
            "routed_rag": routed_rag,
            "elapsed_s": elapsed,
            "failed": bool(fail),
            "empty_return": empty_return,
            # failed router always returns RAG; for this manual-question
            # benchmark that fallback IS the correct route
            "fallback_to_rag": bool(fail) and routed_rag,
            "fail_reason": fail,
        }
        return routed_rag


class RetrievalCapture:
    """Wrap search_hierarchical to record the ranked hits of every call.

    State is per-thread: each worker reads back the captures belonging to the
    question it just ran. With phase-2 decomposition a single question may
    issue several retrieval calls; `calls` accumulates all of them while
    `last` keeps the original single-call schema (the final call).
    """

    def __init__(self):
        self._orig = ap.search_hierarchical
        self._local = threading.local()

    @property
    def calls(self) -> list[dict]:
        return getattr(self._local, "calls", [])

    @property
    def last(self) -> dict | None:
        calls = self.calls
        return calls[-1] if calls else None

    @last.setter
    def last(self, value):
        # Assigning None resets the per-question accumulator (legacy call sites).
        if value is None:
            self._local.calls = []
        else:
            self._local.calls = [value]

    def __call__(self, *args, **kwargs):
        result = self._orig(*args, **kwargs)
        record = {
            "query": args[0] if args else kwargs.get("query"),
            "small_hits": [
                {"chunk_id": h.chunk_id, "rank": h.rank, "score": h.score,
                 "doc_name": h.doc_name, "section_title": h.section_title,
                 "retrieval_source": h.retrieval_source,
                 "scores": h.scores,
                 "content": h.content}
                for h in result.small_hits
            ],
            "mid_hits": [
                {"chunk_id": h.chunk_id, "rank": h.rank, "score": h.score,
                 "doc_name": h.doc_name, "content": h.content}
                for h in result.mid_hits
            ],
            "big_hits": [
                {"chunk_id": h.chunk_id, "rank": h.rank, "score": h.score,
                 "doc_name": h.doc_name, "content": h.content}
                for h in result.big_hits
            ],
            "meta": result.meta.to_dict(),
        }
        if not hasattr(self._local, "calls"):
            self._local.calls = []
        self._local.calls.append(record)
        return result


_KG_LOCK = threading.Lock()


def _install_kg_serializer() -> bool:
    """Serialize KG expansion across worker threads.

    answer.pipeline builds one ChunkExpander per question; each opens .kuzu
    databases read-write. Concurrent opens of the same manual's graph would
    raise inside answer()'s try/except and silently skip KG expansion —
    changing baseline behavior. Holding a lock from construction to close()
    keeps expansion results identical to a sequential run.
    """
    if not getattr(ap, "_KG_AVAILABLE", False):
        return False
    real_expander = ap.ChunkExpander

    class SerializedChunkExpander:
        def __init__(self, *args, **kwargs):
            if not _KG_LOCK.acquire(timeout=600):
                raise RuntimeError("KG serialization lock timeout (600s)")
            self._held = True
            try:
                self._inner = real_expander(*args, **kwargs)
            except BaseException:
                self._release()
                raise

        def _release(self):
            if getattr(self, "_held", False):
                self._held = False
                _KG_LOCK.release()

        def expand(self, *args, **kwargs):
            return self._inner.expand(*args, **kwargs)

        def close(self):
            try:
                self._inner.close()
            finally:
                self._release()

        def __del__(self):
            self._release()

    ap.ChunkExpander = SerializedChunkExpander
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=None, help="run at most N pending questions")
    parser.add_argument("--ids", default=None, help="comma-separated question ids to run")
    parser.add_argument("--lang", choices=["zh", "en"], default=None)
    parser.add_argument("--split-file", default=None,
                        help="frozen split JSONL; when set, only its IDs are run")
    parser.add_argument("--ack-heldout", action="store_true",
                        help="required when --split-file names the formal heldout split")
    parser.add_argument("--warmup-ids", default=None,
                        help="comma-separated non-heldout IDs to run once before measured queries")
    parser.add_argument("--retry-errors", action="store_true",
                        help="re-run ids whose latest record has an error "
                             "(a new record is appended; readers keep the last record per id)")
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent questions (default 1 = sequential)")
    parser.add_argument("--config", default=None,
                        help="answer config yaml (default: answer/configs/default.yaml); "
                             "use for phase-2 ablations without touching the default config")
    args = parser.parse_args()

    out_path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    latest: dict[str, dict] = {}
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    latest[str(rec["id"])] = rec
                except Exception:
                    pass
    done_ids = {qid for qid, rec in latest.items()
                if not (args.retry_errors and rec.get("error"))}

    questions = load_questions(args.lang)
    if args.split_file:
        split_path = ROOT / args.split_file if not Path(args.split_file).is_absolute() else Path(args.split_file)
        if "heldout" in split_path.name.lower() and not args.ack_heldout:
            raise SystemExit("formal Heldout execution requires --ack-heldout")
        split_ids = {
            str(json.loads(line)["id"])
            for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()
        }
        questions = [q for q in questions if q["id"] in split_ids]
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    pending = [q for q in questions if q["id"] not in done_ids]
    if args.limit:
        pending = pending[: args.limit]

    print(f"total={len(questions)} done={len(done_ids)} pending_this_run={len(pending)} "
          f"workers={args.workers}")
    if not pending:
        return

    if args.config:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = ROOT / config_path
        settings = ap.QASettings.load(config_path)
    else:
        settings = ap.QASettings.load()
    capture = RetrievalCapture()
    ap.search_hierarchical = capture  # capture-only proxy; original behavior unchanged
    router_capture = RouterCapture()
    ap.route_question = router_capture  # capture-only proxy; original behavior unchanged

    startup_reload_ms = None
    if settings.retrieval_reload_policy == "startup_once":
        reload_started = time.monotonic()
        ap.retrieval_reload()
        startup_reload_ms = round((time.monotonic() - reload_started) * 1000, 3)
        ap.retrieval_reload = lambda: None
        print(f"retrieval lifecycle: startup_once ({startup_reload_ms}ms)")
    elif args.workers > 1:
        kg_serialized = _install_kg_serializer()
        # answer() calls retrieval_reload() per question; on static artifacts it
        # only rebuilds identical caches. Load once here, then no-op it so a
        # worker cannot drop caches mid-flight under another worker's search.
        ap.retrieval_reload()
        ap.retrieval_reload = lambda: None
        print(f"concurrency guards: kg_serialized={kg_serialized}, retrieval_reload=load-once")

    if args.warmup_ids:
        warmup_wanted = {value.strip() for value in args.warmup_ids.split(",") if value.strip()}
        heldout_ids = {
            str(json.loads(line)["id"])
            for line in (ROOT / "evaluation" / "splits" / "v1" / "heldout.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if warmup_wanted & heldout_ids:
            raise SystemExit("Heldout IDs may not be used for warm-up")
        warmup_questions = [q for q in load_questions() if q["id"] in warmup_wanted]
        for warmup in warmup_questions:
            print(f"warmup id={warmup['id']} (discarded)", flush=True)
            ap.answer(warmup["question"], settings=settings, execution_concurrency=1)
    n_err = 0
    n_done = 0
    write_lock = threading.Lock()

    def run_one(q: dict) -> dict:
        capture.last = None
        router_capture.last = None
        started = time.monotonic()
        telemetry = ap.TraceRecorder(concurrency=args.workers)
        record: dict = {
            "id": q["id"],
            "lang": q["lang"],
            "question": q["question"],
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "workers": args.workers,
            "worker_id": threading.get_ident(),
            "concurrency": args.workers,
            "trace_id": telemetry.trace_id,
            "startup_reload_ms": startup_reload_ms,
            "retrieval_reload_policy": settings.retrieval_reload_policy,
        }
        try:
            result = ap.answer(
                q["question"], settings=settings, telemetry=telemetry,
                execution_concurrency=args.workers,
            )
            record["qa_result"] = result.to_dict()
            record["retrieval"] = capture.last  # None => router sent it down the general path
            if len(capture.calls) > 1:  # phase-2 decomposition: keep every retrieval pass
                record["retrieval_calls"] = capture.calls
            record["router"] = router_capture.last
            record["error"] = None
        except Exception as exc:
            record["qa_result"] = None
            record["retrieval"] = capture.last
            if len(capture.calls) > 1:
                record["retrieval_calls"] = capture.calls
            record["router"] = router_capture.last
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["traceback"] = traceback.format_exc(limit=8)
            record["trace"] = telemetry.to_dict()
        record["wall_seconds"] = round(time.monotonic() - started, 3)
        return record

    with open(out_path, "a", encoding="utf-8") as out:
        if args.workers <= 1:
            for i, q in enumerate(pending, 1):
                record = run_one(q)
                if record["error"]:
                    n_err += 1
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                status = "ERR" if record["error"] else "ok"
                print(f"[{i}/{len(pending)}] id={q['id']} {status} {record['wall_seconds']}s",
                      flush=True)
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(run_one, q): q for q in pending}
                for fut in as_completed(futures):
                    q = futures[fut]
                    try:
                        record = fut.result()
                    except BaseException as exc:  # defensive: run_one should not raise
                        record = {"id": q["id"], "lang": q["lang"], "question": q["question"],
                                  "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "workers": args.workers, "qa_result": None, "retrieval": None,
                                  "router": None, "error": f"harness: {type(exc).__name__}: {exc}",
                                  "wall_seconds": None}
                    with write_lock:
                        n_done += 1
                        if record["error"]:
                            n_err += 1
                        out.write(json.dumps(record, ensure_ascii=False) + "\n")
                        out.flush()
                        status = "ERR" if record["error"] else "ok"
                        print(f"[{n_done}/{len(pending)}] id={record['id']} {status} "
                              f"{record['wall_seconds']}s", flush=True)

    print(f"finished: {len(pending)} run, {n_err} errors -> {out_path}")


if __name__ == "__main__":
    main()
