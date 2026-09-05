# InterX-350 Silver Benchmark — Dataset Governance V1

> This audit treats the 350 Agent-generated references as Silver data. Only explicitly audited records may be marked `verified`.

## Summary

- Questions / answers / joined records: 350 / 350 / 350
- Quality states: `{'silver': 349, 'verified': 1}`
- Coverage: chunk=235, doc=328, image=296
- Duplicate question IDs: `[]`
- Duplicate answer IDs: `[]`
- Fatal audit findings: `{}`
- Warnings: `{'evidence_source_missing': 26, 'id305_format_normalized_semantics_unchanged': 1, 'id65_source_binding_repaired_from_blower_manual': 1}`
- Canonical source dataset hash: `331a2764c09660ae02cc115ff4d12787afd758f48c4b399e5cdb80881b2ba91e`

## Explicit repairs

- **ID 65 — verified source-binding repair.** The prior drill answer was replaced at the per-question source layer with a blower-safety answer grounded only in `吹风机手册.md:54-68,75-111`. Derived aggregates were rebuilt.
- **ID 305 — formatting normalization only.** The malformed `\M\` clean text was normalized to `"M"`; answer semantics were unchanged.

## Interpretation

`silver` means structurally auditable but not authoritative. `verified` applies only to the named audit decision, not to every factual detail in the entire dataset. `quarantined` records are excluded from formal splits and metrics.

The JSON companion contains one record per ID, source existence checks, coverage flags, missing references, and provenance paths.
