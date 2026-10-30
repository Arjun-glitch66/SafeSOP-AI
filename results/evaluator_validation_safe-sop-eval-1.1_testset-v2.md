# EXP-001 — Evaluator validation on injected defects

- Date (UTC): 2026-10-30 10:27
- Evaluator: `safe-sop-eval-1.1` (git `3b45546`)
- Test set: `evaluation/testset.json` — 64 cases (53 with a defect, 11 without)
- Generator: none. Drafts are built from the test set, so ground truth is exact.

## Case-level results

| Metric | Value |
|---|---|
| Status accuracy (fail / needs_review / pass_automated) | 0.734 |
| Exact finding-type match | 0.734 |
| Defect cases flagged (status is not pass_automated) | 0.736 |
| False alarms on defect-free cases | 0.091 |
| Defect cases missed entirely | SOP-CONV/HARD-A-BYPASS-INSERT, SOP-CONV/HARD-B-ALL-TO-MOST, SOP-CONV/HARD-C-CHANGE-IGNORED, SOP-CONV/HARD-INSERT-REACH, SOP-CONV/HARD-ALL-TO-SOME, SOP-ACID/HARD-INSERT-WATER, SOP-ACID/HARD-CHANGE-IGNORED, SOP-ACID/HARD-CHANGE-DROPPED-VALUE, SOP-CENT/HARD-EVERY-TO-SOME, SOP-CENT/HARD-INSERT-OPEN-LID, SOP-FORK/HARD-INSERT-FORKS-RAISED, SOP-FORK/HARD-INSERT-OPERATE-FAILED, SOP-FORK/HARD-CHANGE-IGNORED, SOP-FORK/HARD-ANY-TO-MOST |

## By case group

`hard-dev` cases were known while designing the current rules; `hard-heldout` cases were written before the evaluator version that first targets them (v1.1 or v1.2) and were not used to tune it. They were written by the same author as the rules, so they are held out from tuning, not independent.

| Group | Cases | Correct | Accuracy |
|---|---|---|---|
| hard-dev | 8 | 3 | 0.375 |
| hard-heldout | 24 | 12 | 0.5 |
| standard | 32 | 32 | 1.0 |

## Per finding type

Counted per case (a type is detected or not in each case). 95% intervals: percentile bootstrap over cases, 2000 resamples. Cases built from the same SOP are not independent, so the intervals are optimistic (too narrow). With only a few cases of a type, the interval collapses to a point when every case agrees (for example 2/2 gives [1.0, 1.0]); read that as 'too few cases to estimate', not as certainty.

| Finding type | TP | FP | FN | Precision [95% CI] | Recall [95% CI] |
|---|---|---|---|---|---|
| actor_changed | 0 | 0 | 2 | n/a | 0.0 [0.0, 0.0] |
| altered_step | 1 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| altered_warning | 1 | 1 | 0 | 0.5 [0.0, 1.0] | 1.0 [1.0, 1.0] |
| change_not_applied | 0 | 0 | 4 | n/a | 0.0 [0.0, 0.0] |
| conflicting_instruction | 9 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| contradicts_warning | 0 | 0 | 6 | n/a | 0.0 [0.0, 0.0] |
| duplicated_step | 4 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| missing_warning | 4 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| omitted_step | 5 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| quantifier_weakened | 0 | 0 | 5 | n/a | 0.0 [0.0, 0.0] |
| step_order_violation | 4 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| unsupported_instruction | 4 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| unsupported_value | 7 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |

## Held-out cases only

Cases in group `hard-heldout` (not used to design or tune the current rules). The 'should pass' held-out cases are included, so false alarms count here too.

| Metric | Value |
|---|---|
| Cases | 24 |
| Status accuracy | 0.5 |
| Exact finding-type match | 0.5 |
| Defect cases flagged | 0.389 |
| False alarms on should-pass cases | 0.0 |
| Defect cases missed entirely | SOP-CONV/HARD-INSERT-REACH, SOP-CONV/HARD-ALL-TO-SOME, SOP-ACID/HARD-INSERT-WATER, SOP-ACID/HARD-CHANGE-IGNORED, SOP-ACID/HARD-CHANGE-DROPPED-VALUE, SOP-CENT/HARD-EVERY-TO-SOME, SOP-CENT/HARD-INSERT-OPEN-LID, SOP-FORK/HARD-INSERT-FORKS-RAISED, SOP-FORK/HARD-INSERT-OPERATE-FAILED, SOP-FORK/HARD-CHANGE-IGNORED, SOP-FORK/HARD-ANY-TO-MOST |

| Finding type | TP | FP | FN | Precision [95% CI] | Recall [95% CI] |
|---|---|---|---|---|---|
| actor_changed | 0 | 0 | 1 | n/a | 0.0 [0.0, 0.0] |
| altered_step | 1 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| change_not_applied | 0 | 0 | 3 | n/a | 0.0 [0.0, 0.0] |
| conflicting_instruction | 4 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| contradicts_warning | 0 | 0 | 5 | n/a | 0.0 [0.0, 0.0] |
| quantifier_weakened | 0 | 0 | 3 | n/a | 0.0 [0.0, 0.0] |
| unsupported_value | 2 | 0 | 0 | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |

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
| SOP-CONV/HARD-A-BYPASS-INSERT | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-B-ALL-TO-MOST | quantifier_weakened | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-C-CHANGE-IGNORED | change_not_applied | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-D-ACTOR-LOCK | actor_changed, altered_warning, quantifier_weakened | altered_warning | fail | needs_review | **no** |
| SOP-CONV/HARD-INSERT-REACH | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-ALL-TO-SOME | quantifier_weakened | — | fail | pass_automated | **no** |
| SOP-CONV/HARD-ACTOR-STEP | actor_changed, altered_step | altered_step | fail | needs_review | **no** |
| SOP-CONV/CLEAN-STOP-REWORD | — | — | pass_automated | pass_automated | yes |
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
| SOP-ACID/HARD-INSERT-WATER | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-ACID/HARD-CHANGE-IGNORED | change_not_applied | — | fail | pass_automated | **no** |
| SOP-ACID/HARD-CHANGE-DROPPED-VALUE | change_not_applied | — | fail | pass_automated | **no** |
| SOP-ACID/CLEAN-ANY-TO-EVERY | — | — | pass_automated | pass_automated | yes |
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
| SOP-CENT/HARD-EVERY-TO-SOME | quantifier_weakened | — | fail | pass_automated | **no** |
| SOP-CENT/HARD-INSERT-OPEN-LID | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-CENT/HARD-WARNING-BEFORE-AFTER | conflicting_instruction | conflicting_instruction | fail | fail | yes |
| SOP-CENT/CLEAN-INSPECT-REWORD | — | — | pass_automated | pass_automated | yes |
| SOP-CENT/CLEAN-NEGATED-SAFETY-STEP | — | — | pass_automated | pass_automated | yes |
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
| SOP-FORK/HARD-INSERT-FORKS-RAISED | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-FORK/HARD-INSERT-OPERATE-FAILED | contradicts_warning | — | fail | pass_automated | **no** |
| SOP-FORK/HARD-CHANGE-IGNORED | change_not_applied | — | fail | pass_automated | **no** |
| SOP-FORK/HARD-ANY-TO-MOST | quantifier_weakened | — | fail | pass_automated | **no** |
| SOP-FORK/CLEAN-LIGHTS-REORDER | — | — | pass_automated | pass_automated | yes |

## Reading these results

Standard cases test whether each rule fires on the defect it was designed for, so high scores there are expected and are not evidence of real-world accuracy. The `HARD-*` cases show known blind spots. Real Gemini drafts with human annotation (EXP-002) are needed before claiming real-world performance.
