# Baseline V1 reproduction

Baseline V1 targets Python 3.12 and installs the repository packages from the
root `pyproject.toml`; sibling-package `sys.path` workarounds are therefore not
required in a clean environment. Exact formal dependencies are frozen in
`requirements-baseline-v1.lock`.

```bash
chmod +x scripts/reproduce_baseline_v1.sh
scripts/reproduce_baseline_v1.sh
```

The default invocation rebuilds deterministic Silver/Reference/split artifacts,
validates them, checks secret-file modes, and runs offline tests. It makes no
paid model calls.

Set `INTERX_V1_SMOKE=1` to run two non-Heldout smoke questions after configuring
the direct DashScope and embedding credentials. Set `INTERX_V1_FULL=1` only for a frozen
formal candidate; it runs DEV first and then HELDOUT with the explicit Heldout
acknowledgement. Both use one worker, one query at a time, startup-only corpus
reload, and discarded Train warm-up ID 241.

The offline path safely materializes ignored runtime inputs from the committed
LFS archives and rebuilds `process/artifacts/manual_chunks.db`; the canonical
corpus identity is the deterministic chunk-JSONL tree, not Milvus implementation
metadata. Online smoke/formal execution additionally requires a reachable
DashScope OpenAI-compatible endpoint in `gateway/.env`, the frozen real model
names in `evaluation/configs/baseline_v1.yaml`, and retrieval credentials in
`retrieval/.env`. `provider_probe.py` validates Answer, Rewrite, and Judge
independently before a run. LiteLLM is optional and is not started by the formal
reproduction path.
