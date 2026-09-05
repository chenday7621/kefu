"""One-shot probe: does the gateway's qwen-vl-plus alias accept OpenAI image_url input?"""
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# read gateway .env for the master key
for line in (ROOT / "gateway" / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

img = ROOT / "process" / "data" / "插图" / "Blower_01.png"
b64 = base64.b64encode(img.read_bytes()).decode()
payload = {
    "model": "qwen-vl-plus",
    "max_tokens": 100,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "图里是什么？一句话。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
}
req = urllib.request.Request(
    "http://127.0.0.1:4000/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {os.environ['LITELLM_MASTER_KEY']}",
        "Content-Type": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
        print("HTTP", r.status)
        print("content:", body["choices"][0]["message"]["content"][:200])
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:500])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
    sys.exit(2)
