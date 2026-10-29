# EXP-001 — Evaluator validation on injected defects

- Date (UTC): 2026-10-29 11:08
- Evaluator: `safe-sop-eval-1.0`
- Test set: `evaluation/testset.json` — 42 cases (36 with a defect, 6 without)
- Generator: none. Drafts are built from the test set, so ground truth is exact.

## Case-level results

| Metric | Value |
|---|---|
| Status accuracy (fail / needs_review / pass_automated) | 0.81 |
| Exact finding-type match | 0.81 |
| Defect cases flagged (status is not pass_automated) | 0.806 |
| False alarms on defect-free cases | 0.167 |
| Defect cases missed entirely | SOP-CONV/HARD-ANTONYM, SOP-CONV/HARD-BEFORE-AFTER, SOP-ACID/HARD-ANTONYM-TIGHTEN, SOP-ACID/HARD-UNIT-ML, SOP-CENT/HARD-UNIT, SOP-CENT/HARD-UNIT-KG, SOP-FORK/HARD-ANTONYM-RAISE |

## By case group

`hard-dev` cases were known while designing the current rules; `hard-heldout` cases were written before evaluator v1.1 existed and were not used to tune it.

| Group | Cases | Correct | Accuracy |
|---|---|---|---|
| hard-dev | 4 | 1 | 0.25 |
| hard-heldout | 6 | 1 | 0.167 |
| standard | 32 | 32 | 1.0 |

## Per finding type

| Finding type | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| altered_warning | 0 | 1 | 0 | 0.0 | n/a |
| conflicting_instruction | 4 | 0 | 4 | 1.0 | 0.5 |
| duplicated_step | 4 | 0 | 0 | 1.0 | 1.0 |
| missing_warning | 4 | 0 | 0 | 1.0 | 1.0 |
| omitted_step | 5 | 0 | 0 | 1.0 | 1.0 |
| step_order_violation | 4 | 0 | 0 | 1.0 | 1.0 |
| unsupported_instruction | 4 | 0 | 0 | 1.0 | 1.0 |
| unsupported_value | 4 | 0 | 3 | 1.0 | 0.571 |

## All cases

| Case | Expected | Detected | Expected status | Status | OK |
|---|---|---|---|---|---|
| SOP-CONV/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-CONV/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-CONV/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-CONV/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-CONV/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-CONV/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-CONV/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-CONV/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-CONV/HARD-ANTONYM | conflicting_instruction | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-BEFORE-AFTER | conflicting_instruction | — | fail | pass_automated | **no** |
| SOP-ACID/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-ACID/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-ACID/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-ACID/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-ACID/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-ACID/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-ACID/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-ACID/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-ACID/HARD-PARAPHRASE | — | altered_warning | pass_automated | needs_review | **no** |
| SOP-ACID/HARD-ANTONYM-TIGHTEN | conflicting_instruction | — | fail | pass_automated | **no** |
| SOP-ACID/HARD-UNIT-ML | unsupported_value | — | fail | pass_automated | **no** |
| SOP-CENT/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-CENT/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-CENT/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-CENT/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-CENT/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-CENT/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-CENT/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-CENT/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-CENT/HARD-UNIT | unsupported_value | — | fail | pass_automated | **no** |
| SOP-CENT/HARD-UNIT-KG | unsupported_value | — | fail | pass_automated | **no** |
| SOP-CENT/HARD-SAFE-REORDER-CLAUSE | — | — | pass_automated | pass_automated | yes |
| SOP-FORK/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-FORK/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-FORK/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-FORK/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-FORK/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-FORK/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-FORK/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-FORK/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-FORK/HARD-INTENDED-REMOVAL | omitted_step | omitted_step | needs_review | needs_review | yes |
| SOP-FORK/HARD-ANTONYM-RAISE | conflicting_instruction | — | fail | pass_automated | **no** |

## Reading these results

Standard cases test whether each rule fires on the defect it was designed for, so high scores there are expected and are not evidence of real-world accuracy. The `HARD-*` cases show known blind spots. Real Gemini drafts with human annotation (EXP-002) are needed before claiming real-world performance.
