"""Offline unit checks for phase-2 pipeline helpers (_rrf_merge / _merge_hierarchical).

No network, no Milvus — synthesizes SearchHit-like dataclasses via the real
retrieval.types, loaded directly from file to skip retrieval/__init__ (which
pulls in requests/pymilvus not present in the answer venv). Run from anywhere:
  answer/.venv/bin/python evaluation/scripts/test_rrf_merge.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))

# Load retrieval.types as a standalone module (stdlib-only file) without
# executing retrieval/__init__.py.
_types_spec = importlib.util.spec_from_file_location(
    "retrieval_types", ROOT / "retrieval" / "src" / "retrieval" / "types.py")
_types = importlib.util.module_from_spec(_types_spec)
sys.modules["retrieval_types"] = _types  # dataclass() looks the module up in sys.modules
_types_spec.loader.exec_module(_types)
HierarchicalResult, SearchHit = _types.HierarchicalResult, _types.SearchHit

# answer.pipeline also imports retrieval at module level; register the stub
# package so `from retrieval import ...` resolves without heavy deps.
import types as _pytypes  # noqa: E402

_retrieval_stub = _pytypes.ModuleType("retrieval")
_retrieval_stub.reload = lambda: None
_retrieval_stub.search_hierarchical = lambda *a, **k: None
sys.modules.setdefault("retrieval", _retrieval_stub)
sys.modules.setdefault("retrieval.types", _types)

from answer.pipeline import _merge_hierarchical, _rrf_merge  # noqa: E402


def make_hit(cid: str, rank: int, doc: str = "docA") -> SearchHit:
    return SearchHit(
        chunk_id=cid, score=1.0 / rank, rank=rank, doc_id=doc, doc_name=doc,
        product_name=doc, content=f"content-{cid}", retrieval_text="",
        image_abs_paths=[], token_count=10, section_title="", header_path=[],
        big_chunk_id="", mid_chunk_id="", retrieval_source="rerank",
    )


def test_dedup_and_shared_chunk_wins():
    a = [make_hit("c1", 1), make_hit("c2", 2), make_hit("c3", 3)]
    b = [make_hit("c9", 1), make_hit("c1", 2), make_hit("c8", 3)]
    merged = _rrf_merge([a, b], cap=10)
    ids = [h.chunk_id for h in merged]
    assert len(ids) == len(set(ids)), "duplicate chunk_id after merge"
    # c1 appears in both lists (rank 1 + rank 2) -> highest RRF mass
    assert ids[0] == "c1", f"expected shared chunk first, got {ids}"
    # ranks must be contiguous 1..n
    assert [h.rank for h in merged] == list(range(1, len(merged) + 1))
    # scores descending
    scores = [h.score for h in merged]
    assert scores == sorted(scores, reverse=True)
    print("test_dedup_and_shared_chunk_wins OK", ids)


def test_cap():
    a = [make_hit(f"a{i}", i) for i in range(1, 8)]
    b = [make_hit(f"b{i}", i) for i in range(1, 8)]
    merged = _rrf_merge([a, b], cap=5)
    assert len(merged) == 5, f"cap failed: {len(merged)}"
    print("test_cap OK")


def test_single_list_preserves_order():
    a = [make_hit("x1", 1), make_hit("x2", 2), make_hit("x3", 3)]
    merged = _rrf_merge([a], cap=10)
    assert [h.chunk_id for h in merged] == ["x1", "x2", "x3"]
    print("test_single_list_preserves_order OK")


def test_merge_hierarchical():
    def hr(prefix: str) -> HierarchicalResult:
        return HierarchicalResult(
            query=f"q-{prefix}",
            small_hits=[make_hit(f"{prefix}s{i}", i) for i in range(1, 4)],
            mid_hits=[],
            big_hits=[],
            meta=None,  # _merge_hierarchical never touches meta internals
        )

    p1, p2 = hr("p1"), hr("p2")
    p2.small_hits.append(make_hit("p1s1", 4))  # overlap with p1's top hit
    merged = _merge_hierarchical([p1, p2], small_cap=5, mid_cap=3, big_cap=2)
    ids = [h.chunk_id for h in merged.small_hits]
    assert len(merged.small_hits) == 5
    assert ids[0] == "p1s1", f"shared chunk should win: {ids}"
    assert merged.mid_hits == [] and merged.big_hits == []
    print("test_merge_hierarchical OK", ids)


if __name__ == "__main__":
    test_dedup_and_shared_chunk_wins()
    test_cap()
    test_single_list_preserves_order()
    test_merge_hierarchical()
    print("ALL PASS")
