"""Phase-2 VLM end-to-end test: user image -> structured extraction -> retrieval -> answer.

Four scenarios against the full answer() pipeline with vlm.enabled=true
(config: answer/configs/ablation_vlm.yaml):

  S1 air-fryer photo + matching question   -> extraction sane, answer on-topic
  S2 AC-indoor-unit photo + matching q     -> same, zh manual routing
  S3 conflict: AC photo but text claims dishwasher -> answer must flag the mismatch
  S4 degradation: VLM pointed at a bogus model     -> answer still produced, vlm_extraction None

Run:  chat/.venv/bin/python evaluation/scripts/test_vlm_e2e.py [s1|s2|s3|s4|all]
Writes full records to /tmp/vlm_e2e_results.jsonl for inspection.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "answer" / "src"))
sys.path.insert(0, str(ROOT / "retrieval" / "src"))
sys.path.insert(0, str(ROOT / "kg" / "src"))

import answer.pipeline as ap  # noqa: E402

IMG_DIR = ROOT / "data" / "ch-manual" / "插图"
AIR_FRYER = str(IMG_DIR / "air_fryer_05.png")
AC_UNIT = str(IMG_DIR / "Manual01_6.jpg")
OUT = Path("/tmp/vlm_e2e_results.jsonl")

SCENARIOS = {
    "s1": {
        "question": "这个提示音一直响是什么情况，怎么关掉？",
        "images": [AIR_FRYER],
        "expect": "空气炸锅相关回答；vlm_extraction.product_category 指向空气炸锅/厨房电器",
    },
    "s2": {
        "question": "遥控器对着它没反应，怎么排查？",
        "images": [AC_UNIT],
        "expect": "空调相关回答；product_category 指向空调",
    },
    "s3": {
        "question": "我的洗碗机洗完之后有白色残留怎么办？",
        "images": [AC_UNIT],
        "expect": "答案应提示图片显示的是空调类产品、与文字描述（洗碗机）不一致",
    },
    "s4": {
        "question": "空气炸锅第一次使用前要做什么准备？",
        "images": [AIR_FRYER],
        "expect": "VLM 配置故意损坏 -> vlm_extraction 为 None，但答案照常生成（降级验证）",
        "break_vlm": True,
    },
}


def run_scenario(key: str, settings) -> dict:
    sc = SCENARIOS[key]
    if sc.get("break_vlm"):
        settings = dataclasses.replace(
            settings, vlm_llm=dataclasses.replace(settings.vlm_llm, model_name="no-such-model"),
        )
    t0 = time.monotonic()
    result = ap.answer(sc["question"], settings=settings, user_images=sc["images"])
    elapsed = round(time.monotonic() - t0, 1)
    meta = result.recall_meta
    record = {
        "scenario": key,
        "question": sc["question"],
        "images": [Path(p).name for p in sc["images"]],
        "expect": sc["expect"],
        "elapsed_s": elapsed,
        "vlm_extraction": meta.vlm_extraction,
        "sub_questions": meta.sub_questions,
        "final_answer": result.final_answer.content,
        "answer_images": result.final_answer.images,
        "top5_docs": [],
    }
    print(f"\n===== {key} ({elapsed}s) =====")
    print("Q:", sc["question"], "| img:", record["images"])
    ve = meta.vlm_extraction
    if ve:
        for field, v in ve.items():
            if v.get("value"):
                print(f"  VLM {field}: {v['value'][:60]!r} conf={v['confidence']}")
    else:
        print("  VLM extraction: None")
    print("  answer head:", result.final_answer.content[:200].replace("\n", " "))
    return record


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    keys = list(SCENARIOS) if which == "all" else [which]
    settings = ap.QASettings.load("configs/ablation_vlm.yaml")
    assert settings.vlm.enabled, "ablation_vlm.yaml must have vlm.enabled: true"

    records = []
    for key in keys:
        try:
            records.append(run_scenario(key, settings))
        except Exception as exc:
            import traceback
            records.append({"scenario": key, "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(limit=6)})
            print(f"===== {key} FAILED: {exc}")

    with open(OUT, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nrecords -> {OUT}")
    n_err = sum(1 for r in records if r.get("error"))
    print(f"done: {len(records)} scenarios, {n_err} errors")


if __name__ == "__main__":
    main()
