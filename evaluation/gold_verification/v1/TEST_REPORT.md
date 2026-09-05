# Gold Verification Infrastructure Test Report

- Candidate source commit: `ecc33679d0fc993b60cea0abb8566633875b431f`
- Test command: `.venv-baseline-v1/bin/python -m pytest -q`
- Result: **123 passed, 21 skipped, 2 warnings**
- Infrastructure-specific tests: **9 passed**
- Formal DEV run: **not executed**
- Formal Heldout run: **not executed**
- Human decisions created automatically: **0**
- Verified preview records: **0**

The 21 skips are pre-existing KG runtime tests whose graph databases are not built in this Candidate worktree. Baseline V1 keeps runtime KG disabled. The two warnings are dependency deprecations from Starlette/FastAPI test tooling.

Covered contracts include frozen split IDs and no overlap, source-span extraction, schema/record validation, CSV round-trip, human-decision requirements, incomplete-build refusal, explicit Heldout seal acknowledgement, deterministic line-overlap chunk remapping, and absence of runtime-output fields in human-facing review assets.
