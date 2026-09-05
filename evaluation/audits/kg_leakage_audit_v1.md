# KG Leakage Audit V1

- QA-derived source: **Train only**
- Mapped evidence records: 1315
- Retained semantic edges: 762
- Dev answer-ID overlap: 0
- Heldout answer-ID overlap: 0
- Input leakage audit: **PASS**
- Official Baseline V1 policy: **KG disabled** until the new graph path is
  explicitly selected by runtime configuration and an end-to-end trace confirms
  that no legacy graph database is opened.

Filtering `CO_EVIDENCE` inputs is insufficient by itself; this script also filters
the QA-derived `SEMANTIC` edges by `answer_id`. The frozen split uses connected
manual components, so no atomic manual is shared across Train, Dev, or Heldout.
