# Human Judge Rubric V1

Reviewers do not receive a system version name. Score every dimension from 1 to 5.

- **Answer correctness:** factual agreement with source evidence and reference.
- **Completeness:** coverage of material answer elements supported by evidence.
- **Faithfulness:** no factual assertion beyond the supplied source evidence.
- **Binary accept:** `1` only if correctness and faithfulness are both at least 4;
  otherwise `0`.

If source evidence is empty, faithfulness must be scored `1` and the limitation
recorded in notes. Do not use outside knowledge. The calibration subset may be
used to revise the Judge rubric/prompt. The validation subset is evaluated only
after that revision is frozen. Neither subset is the model-quality Heldout split.
