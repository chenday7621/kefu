"""Phase-1 smoke test: 3 manual QA questions via chat API (dense + rerank enabled)."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = "sk_local_dev"


def chat(question: str, session_id: str | None = None) -> dict:
    body = {"question": question}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read())
    elapsed = time.time() - start
    data = payload.get("data", payload)
    return {
        "code": payload.get("code"),
        "elapsed": round(elapsed, 1),
        "session_id": data.get("session_id"),
        "answer": data.get("answer", ""),
        "image_ids": data.get("image_ids", []),
    }


def report(tag: str, r: dict) -> None:
    ans = r["answer"]
    ok = r["code"] == 0 and len(ans) > 50
    print(f"\n===== {tag} {'PASS' if ok else 'FAIL'} =====")
    print(f"code={r['code']} time={r['elapsed']}s len={len(ans)} "
          f"PIC={ans.count('<PIC>')} images={r['image_ids']} session={r['session_id']}")
    print(ans[:300].replace("\n", " "))


r1 = chat("空调制冷效果不太好怎么办？")
report("Test1 中文/空调", r1)

r2 = chat("How do I use the air fryer for the first time?")
report("Test2 英文/air fryer", r2)

r3 = chat("滤网在哪里？怎么拆下来清洗？", session_id=r1["session_id"])
report("Test3 多轮/指代消解", r3)

passed = sum(1 for r in (r1, r2, r3) if r["code"] == 0 and len(r["answer"]) > 50)
print(f"\n===== 总计 {passed}/3 通过 =====")
