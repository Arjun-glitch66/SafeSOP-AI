# EXP-001 — Evaluator validation on injected defects

- Date (UTC): 2026-10-29 11:48
- Evaluator: `safe-sop-eval-1.1`
- Test set: `evaluation/testset.json` — 42 cases (36 with a defect, 6 without)
- Generator: none. Drafts are built from the test set, so ground truth is exact.

## Case-level results

| Metric | Value |
|---|---|
| Status accuracy (fail / needs_review / pass_automated) | 0.976 |
| Exact finding-type match | 0.976 |
| Defect cases flagged (status is not pass_automated) | 1.0 |
| False alarms on defect-free cases | 0.167 |
| Defect cases missed entirely | none |

## By case group

`hard-dev` cases were known while designing the current rules; `hard-heldout` cases were written before evaluator v1.1 existed and were not used to tune it.

| Group | Cases | Correct | Accuracy |
|---|---|---|---|
| hard-dev | 4 | 3 | 0.75 |
| hard-heldout | 6 | 6 | 1.0 |
| standard | 32 | 32 | 1.0 |

## Per finding type

| Finding type | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| altered_warning | 0 | 1 | 0 | 0.0 | n/a |
| conflicting_instruction | 8 | 0 | 0 | 1.0 | 1.0 |
| duplicated_step | 4 | 0 | 0 | 1.0 | 1.0 |
| missing_warning | 4 | 0 | 0 | 1.0 | 1.0 |
| omitted_step | 5 | 0 | 0 | 1.0 | 1.0 |
| step_order_violation | 4 | 0 | 0 | 1.0 | 1.0 |
| unsupported_instruction | 4 | 0 | 0 | 1.0 | 1.0 |
| unsupported_value | 7 | 0 | 0 | 1.0 | 1.0 |

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
| SOP-CONV/HARD-ANTONYM | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-CONV/HARD-BEFORE-AFTER | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-ACID/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-ACID/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-ACID/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-ACID/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-ACID/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-ACID/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-ACID/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-ACID/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-ACID/HARD-PARAPHRASE | — | altered_warning | pass_automated | needs_review | **no** |
| SOP-ACID/HARD-ANTONYM-TIGHTEN | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-ACID/HARD-UNIT-ML | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-CENT/CLEAN | — | — | pass_automated | pass_automated | yes |
| SOP-CENT/MISSING-WARNING | missing_warning | missing_warning | fail | fail | yes |
| SOP-CENT/ORDER-SWAP | step_order_violation | step_order_violation | fail | fail | yes |
| SOP-CENT/UNSUPPORTED-STEP | unsupported_instruction | unsupported_instruction | fail | fail | yes |
| SOP-CENT/UNSUPPORTED-VALUE | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-CENT/OMITTED-STEP | omitted_step | omitted_step | fail | fail | yes |
| SOP-CENT/DUPLICATED-STEP | duplicated_step | duplicated_step | needs_review | needs_review | yes |
| SOP-CENT/CONFLICT-NEGATION | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-CENT/HARD-UNIT | unsupported_value | unsupported_value | fail | fail | yes |
| SOP-CENT/HARD-UNIT-KG | unsupported_value | unsupported_value | fail | fail | yes |
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
| SOP-FORK/HARD-ANTONYM-RAISE | conflicting_instruction | conflicting_instruction | fail | fail | yes |

## Reading these results

Standard cases test whether each rule fires on the defect it was designed for, so high scores there are expected and are not evidence of real-world accuracy. The `HARD-*` cases show known blind spots. Real Gemini drafts with human annotation (EXP-002) are needed before claiming real-world performance.
