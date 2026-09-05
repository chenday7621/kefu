# InterX Human Gold Review Rubric V1

This rubric governs manual review of the Dev and Heldout proposal sheets. Automatic warnings help prioritize inspection but never determine a decision.

## Blinding rule

Reviewers use only the question, Candidate Silver answer, original-manual evidence, proposed facts, proposed images, and deterministic source-to-chunk mapping. Runtime model responses and retrieval diagnostics must not be added to these sheets.

## Field decisions

### Question valid

- `true`: the question is intelligible and answerable from the in-scope product manuals.
- `false`: it is malformed, materially ambiguous, out of scope, or cannot be grounded in the available source corpus.

### Reference answer

- `APPROVE`: every material claim is supported by accepted source evidence, the answer addresses the question, and there is no material contradiction or omission.
- `EDIT`: enter a complete corrected answer in `human_reference_answer_final` using only accepted source evidence.
- `REJECT`: do not approve the record; use `QUARANTINE` or `NEEDS_SECOND_REVIEW` as appropriate.

Wording differences are allowed. Unsupported additions, wrong product facts, unsafe instructions, or meaning-changing omissions are not.

### Required facts

A required fact is an atomic fact needed for a materially correct answer. It must be directly supported by accepted source evidence.

- `APPROVE`: the proposed list is complete, atomic enough to score, and source-supported.
- `EDIT`: enter the complete replacement list as JSON in `human_required_facts_final_json`.

Machine-proposed facts are excerpts selected conservatively by lexical overlap. They are not authoritative and may be incomplete.

### Source evidence

- `APPROVE`: manual identity, section/location, source lines, and displayed text identify sufficient authoritative support.
- `EDIT`: enter replacement evidence objects in `human_source_evidence_final_json`.
- `N/A`: allowed only where the review policy explicitly accepts that no source evidence is required; explain in notes.
- `UNRESOLVED`: provide `human_source_evidence_unresolved_reason`; the record cannot silently become approved.

A located source span is merely a proposal. Reviewers must inspect whether it actually supports the answer.

### Images

- `APPROVE`: proposed image IDs correspond to the source/manual and are necessary or acceptable for the answer.
- `EDIT`: enter the corrected list in `human_image_final_json`.
- `N/A`: no image is required.

### Chunk mapping

- `APPROVE`: current-corpus mappings cover each accepted evidence group.
- `EDIT`: enter replacement mapping in `human_chunk_mapping_final_json`, derived from accepted source spans.
- `UNRESOLVED_ACCEPTED`: source evidence is valid but the current corpus cannot be mapped deterministically; explain in notes.

Chunk IDs are derivative and must not override Source Gold.

## Overall decision

- `APPROVE`: all candidate fields are accepted under the validator requirements.
- `EDITED_APPROVE`: final answer, final required facts, and edited evidence (or explicit unresolved reason) are present and all remaining fields have been reviewed.
- `QUARANTINE`: the record must not enter Human-Verified Gold; `human_quarantine_reason` is required.
- `NEEDS_SECOND_REVIEW`: disagreement or uncertainty remains; notes are required and the record cannot enter Gold.

For every non-null decision, set `human_review_status=COMPLETED`, `human_reviewer_id`, and an ISO-8601 `human_reviewed_at` timestamp. The validator checks structure and decision completeness; it does not judge truth.
