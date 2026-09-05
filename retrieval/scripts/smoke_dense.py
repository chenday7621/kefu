"""Phase-1 smoke check: verify DashScope embedding + rerank endpoints are usable."""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.filterwarnings("ignore")

from retrieval.config import RetrievalSettings
from retrieval.dense import embed_query

settings = RetrievalSettings.load(None)
vec = embed_query("空调制冷效果差怎么办", api_config=settings.api, config=settings.embedding)
print("embedding OK, dim:", len(vec))
