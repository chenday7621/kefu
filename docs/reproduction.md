# Reproduction boundaries

Python 3.12; the six core runtime files use stdlib until official integration is invoked.
The public CLI and core tests do not require credentials, private corpora or tau2.

For offline official-interface tests, install official tau2-bench outside this repository:

```bash
git clone https://github.com/sierra-research/tau2-bench ../tau2-bench
cd ../tau2-bench
git checkout --detach fc0055dc4e0a316c3f83133267fbd6faaa770992
uv sync
cd ../kefu-agent-public
TAU2_ROOT=../tau2-bench .venv/bin/python -m pytest -q
```

The optional test uses fake model responses and a real official environment tool;
it does not load official test tasks or invoke a provider/user simulator/scorer LLM.
This verifies interface, validation and identity wiring, not fresh task performance.

Live integration uses `build_kefu_agent_factory` registered with official tau2, and
`AgentIdentityMonitor.guard()` around the official session. User simulation and scorer
remain official. Provider credentials belong in private environment variables.
No live runner is bundled here: the internal certified runner requires private
provenance and fixed output paths and is intentionally excluded. Consequently this
release is reproducible at the source/contract/aggregate-integrity level, not a
turnkey reproduction of the private historical 40-task trajectories or exact 80%.
