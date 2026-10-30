# SAFE-SOP Evaluation Framework (v1.2)

Implementation: `src/safety_evaluator.py` → `evaluate_revision()` · version tag `safe-sop-eval-1.2`

| Version | Change | Evidence |
|---|---|---|
| 1.0 | §2.1–2.4 as first defined | EXP-001 (logbook entry 2) |
| 1.1 | Added the opposite-word check (§2.5) and the number+unit check (§2.4); merged steps are no longer counted as an order reversal (§2.3) | EXP-001b (logbook entry 4) |
| 1.2 | Added warning-contradiction, quantifier, actor and change-applied checks (§2.6); `all`, `any`, `each`, `before`, `after` are no longer stop-words; new `high` severity | EXP-001c (logbook entry 9) |

This framework checks an AI-generated SOP draft against the **immutable original SOP** and the **engineer's change request**. It does not decide whether a procedure is safe. It decides whether the draft shows evidence of specific, well-defined failure types. Only a qualified human reviewer can approve a draft.

## 1. Inputs and what is evaluated

| Input | Source |
|---|---|
| Original text *O* | Text extracted from the uploaded PDF (full document, or the selected page) |
| Change request *C* | The engineer's description of the process change |
| Generated output *G* | The full model response. Only the `DRAFT:` section is evaluated. |

The model's own `PRESERVED SAFETY REQUIREMENTS` section is **ignored**. A draft is never credited for warnings the model *claims* it kept.

### 1.1 Extraction rules

- **Lines.** Markdown symbols (`* _ # \` >`) and leading bullets are removed, and blank lines are dropped.
- **Steps.** A step is a line that starts with a number such as `3.`, `3)`, `3.1.` or `Step 3`.
- **Warnings.** A warning is a non-step line that contains a hazard keyword (`warning, caution, danger, hazard, do not, never, must not, emergency, lockout, tagout, ppe, protective`) and has at least 3 content words. This excludes bare headings such as "SAFETY WARNINGS".
- **Tokens.** Tokens are the lower-case alphabetic words in a line, after removing stop-words, negation words and hazard labels (`warning`, `caution`, …), and with a naive plural strip. Numbers are not tokens; they are checked separately (§2.4).
- **Negation.** A line is negated if it contains `not, never, no, don't, cannot` or `nor`.

### 1.2 Similarity measures

For token sets *A* and *B*:

- **Containment** (how much of *A* appears in *B*): cont(*A*, *B*) = |*A* ∩ *B*| / |*A*|
- **Dice similarity** (two-way overlap): dice(*A*, *B*) = 2|*A* ∩ *B*| / (|*A*| + |*B*|)

### 1.3 Thresholds

| Name | Value | Meaning |
|---|---|---|
| τ_match | 0.80 | At or above this, the item counts as preserved or matched |
| τ_partial | 0.50 | From 0.50 up to τ_match, the item counts as altered and is flagged for review |
| τ_dup | 0.90 | Two draft steps with Dice similarity at or above this are duplicates |

These are fixed **before** results are reported. Changing them creates a new evaluator version.

## 2. Metrics

Let *W* be the set of source warnings, *S* the source steps (in order) and *D* the draft steps (in order).

### 2.1 Warning preservation and warning recall

For each warning *w* ∈ *W*, take its best containment score over all draft lines: *s_w* = max over lines ℓ of cont(tok(*w*), tok(ℓ)).

- **Preserved:** *s_w* ≥ τ_match
- **Altered:** τ_partial ≤ *s_w* < τ_match. This produces an `altered_warning` finding (review).
- **Missing:** *s_w* < τ_partial. This produces a `missing_warning` finding (critical).

**Warning recall** = |preserved| / |*W*|

**Lenient warning recall** = (|preserved| + |altered|) / |*W*|

Containment is used rather than Dice because a warning merged into a longer sentence still counts as preserved.

### 2.2 Step mapping: omitted, altered, duplicated and conflicting steps

Each source step *s* is mapped to the draft step with the highest Dice score *d_s*.

| Condition | Finding | Severity |
|---|---|---|
| *d_s* < τ_partial | `omitted_step` | critical, or **review** if cont(tok(*s*), tok(*C*)) ≥ τ_partial, meaning the change request appears to ask for the removal |
| τ_partial ≤ *d_s* < τ_match, and the new words are contained in *C* (≥ τ_match) | `altered_step` | info (the requested change) |
| τ_partial ≤ *d_s* < τ_match, otherwise | `altered_step` | review |
| Negation differs between *s* and its match, or an opposite-word swap (§2.5) | `conflicting_instruction` | critical, or **review** if the change request contains the new word |
| Two draft steps with dice ≥ τ_dup | `duplicated_step` | review |

The negation check is also applied to each matched warning.

**Step coverage** = |{*s* : *d_s* ≥ τ_partial}| / |*S*|

### 2.3 Step-order integrity

Let *P* be the source steps that were found in the draft, in source order, each with its draft position π(*s*).

**Order integrity** = |{(*i*, *j*) : *i* < *j*, π(*s_i*) < π(*s_j*)}| / C(|*P*|, 2)

This is the fraction of source step pairs whose relative order is kept, a pairwise-concordance measure similar to Kendall's τ rescaled to [0, 1]. Any inverted pair produces a `step_order_violation` finding (critical). From v1.1, a pair whose two steps map to the **same** draft step (two steps merged into one, π(*s_i*) = π(*s_j*)) counts as concordant, not as a reversal.

### 2.4 Unsupported instructions and values (hallucination detection)

A draft step *d* is **supported** if its tokens are mostly found in one source line together with the change request:

support(*d*) = max over source lines ℓ of cont(tok(*d*), tok(ℓ) ∪ tok(*C*))

- If support(*d*) < τ_partial, the step is an `unsupported_instruction` (critical).
- **Unsupported instruction rate** = |unsupported draft steps| / |*D*|
- Any number in a draft step or a draft warning that appears in neither *O* nor *C* is an `unsupported_value` (critical). Invented values such as torques, temperatures and times are the most dangerous kind of hallucination in an SOP.
- **Unit check (v1.1).** Numbers followed by a recognised unit form (number, unit) pairs, e.g. (3000, rpm). The units cover pressure, length, mass, volume, electrical units, speed, time, percent and °C/°F; ambiguous single letters (m, g, l, s) are left out. If a draft pair uses a number that appears with a unit in *O* or *C*, but with a unit that number never has there, it is an `unsupported_value` (critical). Example: source "3000 rpm", draft "3000 rcf".

### 2.5 Opposite words (v1.1)

A fixed list of opposite-meaning pairs (on/off, open/close, raise/lower, start/stop, before/after, tighten/loosen, increase/decrease, enable/disable, connect/disconnect, lock/unlock, above/below, minimum/maximum, engage/disengage) is checked for every matched warning and step. If the source uses one word of a pair and the draft uses only the other, the result is a `conflicting_instruction`. These swaps keep almost every token, so §2.2's overlap scores cannot see them.

### 2.6 Meaning checks (v1.2)

Four rules for failures that keep most tokens, so §2.1–2.5 pass them. Each finding quotes its evidence (`source`, `draft`, `evidence`) with the 1-based line numbers in the original text and in the draft section (`source_line`, `draft_line`).

| Finding | Severity | Rule |
|---|---|---|
| `contradicts_warning` | critical | Every source warning that forbids something ("do not / never / must not" + verb + object, optionally "while / when / with / without / that / if …" + condition) is compared with **every** draft step, including new ones. A step without negation that uses the verb (crude stem match), contains ≥ 50 % of the object tokens, and, if the warning has a condition, ≥ 50 % of the condition tokens, does what the warning forbids. |
| `quantifier_weakened` | critical (review if the change request uses the weaker word) | In a matched warning or step, a strong word (all, every, each, always, before) disappears and a weaker one (some, most, a, single, few, sometimes, after, during, while, once, …) appears. `before → after` alone is already a `conflicting_instruction` (§2.5) and is not reported twice. |
| `actor_changed` | high (review if requested) | In a matched lock, tag, isolation, permit, sign-off or verification line, the named performer changes (worker, operator, supervisor, technician, you, …). Lines that name nobody in the source are not checked. |
| `change_not_applied` | critical | The draft section equals the original, or none of the change request's **new** numbers and terms (not in the original, not instruction words such as "replace" or "increase") appear in the draft. Removal requests are only checked for an unchanged draft. |

### 2.7 Structured matching for prompt-v3 drafts

From prompt v3 the source's warnings and steps are numbered (W1…, S1…) in the prompt, and the model returns every draft step and warning as JSON that cites those ids (`source_step_ids`, `source_warning_id`), with a `change_type` per step and a `removed_warning_ids` list. `evaluate_structured_revision()` (reported as `safe-sop-eval-1.2+structured`) matches by id instead of by text similarity, so §2.1–2.3 no longer depend on regex extraction of the draft:

| Rule | Finding |
|---|---|
| A source warning not cited by any draft warning and not in `removed_warning_ids` | `missing_warning` (critical) |
| A source warning in `removed_warning_ids` | `warning_removed` (critical): a declared removal is still a lost warning until a reviewer confirms the hazard is gone |
| A source step not cited by any draft step | `omitted_step` (critical) |
| A step with `change_type: removed` | `omitted_step` (critical; review if the change request asks for it) |
| A step labelled `unchanged` whose text differs from its source | `altered_step` (review): the model's label is not trusted |
| A draft item citing an id the source does not have | `invalid_source_reference` (review) |
| Every kept step, including `added` ones, against every source prohibition | `contradicts_warning` (§2.6) |

Opposite words, quantifier, actor, value, unit, duplicate, order and change-applied checks are the same as in the text path, run on the cited pairs and on the rendered draft. Versions without stored JSON (prompt v1/v2) keep the text path.

## 3. Decision rule

| Status | Condition |
|---|---|
| `fail` | At least one **critical** or **high** finding |
| `needs_review` | No critical or high findings, but at least one **review** finding |
| `pass_automated` | No critical, high or review findings |

`high` (v1.2) fails a draft exactly like `critical`. It marks findings that rest on a rougher heuristic (who performs a step), so reviewers can read them after the critical ones.

`pass_automated` means *no rule fired*. It does **not** mean safe or approved. Every status leads to human review. The approval decision is recorded separately, in `review_history`.

## 4. Handling uncertainty

The evaluator never turns uncertainty into a pass:

- Scores between τ_partial and τ_match are reported as *altered* (review), not as preserved and not as missing.
- If no steps or no warnings are detected in the source, the evaluator emits `no_source_steps_detected` or `no_source_warnings_detected` (review), and the related metric is reported as `null`, not as 100%.
- If the model output has no `DRAFT:` section, the evaluator emits `draft_section_not_found` (review) and evaluates the whole response.
- A step removal that the change request appears to ask for is still flagged (review) for a human to confirm.

## 5. Worked examples

These are taken from `evaluation/testset.json`.

| Draft change | Result |
|---|---|
| Acid SOP: flush volume changed from 5 to 10 litres, as requested | `pass_automated`. 10 appears in *C*, so it is not an unsupported value. |
| Conveyor SOP: warning "Never reach into the conveyor…" deleted | `missing_warning` (critical), status `fail`, warning recall 0.75 |
| Steps 4 and 5 swapped | `step_order_violation` (critical). Order integrity is 27/28 = 0.964 for 8 steps. |
| "Stop the conveyor…" becomes "Do not stop the conveyor…" | `conflicting_instruction` (critical) |
| " for 47 seconds" appended to a step | `unsupported_value` [47] (critical) |
| Forklift SOP: horn-test step removed, and the change request asks for this | `omitted_step` (review), status `needs_review` |

## 6. Annotation rules for human evaluation (EXP-002 and later)

Automated findings are candidates and need confirming. For each row of `results/<EXP>_annotation.csv` (one row per source warning or step, per run), **two annotators work independently**. Each reads the full draft and fills in their own column (`human_label_a` or `human_label_b`) without looking at the other's:

| Item | Label | Rule |
|---|---|---|
| Warning | `preserved` | Same hazard, same required action, same strength (e.g. "never" is not weakened to "avoid"). Wording may differ. |
| Warning | `altered` | Still present, but the hazard, the action or the strength changed |
| Warning | `missing` | Not present anywhere in the draft |
| Step | `present` | The same action, in a position that keeps every prerequisite before it |
| Step | `altered` | The action changed. Write `intended` in `notes` if the change request asked for it. |
| Step | `missing` | Not present, and the change request did not ask for its removal |

Add a note for any step or value in the draft that does not come from the source or the change request: `unsupported: <text>`. Where reviewers disagree, they discuss and record the agreed label. If it is still unclear, they record `uncertain` (this counts as not preserved in safety metrics).

The automated evaluator's agreement with these labels is the real-world measure of the evaluator. `evaluation/agreement.py` reports:

- **Cohen's κ** between the two annotators: κ = (p_o − p_e) / (1 − p_e), where p_o is observed agreement and p_e is chance agreement from each annotator's label frequencies.
- Evaluator **accuracy** against the consensus label, per item type. `preserved` and `present` are both counted as "kept".
- **Problem recall**: of the items humans labelled altered, missing or uncertain, the share the evaluator flagged as altered or missing. Also **missing recall**.
- The **false-alarm rate** on items humans marked as kept, and a list of every **dangerous miss** (a human found a problem, the evaluator said kept).

Rows where the two annotators disagree are excluded until they are resolved by discussion.

### 6.1 Draft-item annotation (EXP-003 on)

The source-item format above cannot record content the model *added*. From EXP-003, annotators label **each draft step and warning** as `supported`, `unsupported` (new content not backed by the source or the change request) or `contradicting` (goes against the source), and map it to the source item(s) it comes from (`W1`, `S4`, …; empty for a new item). Source items that no draft item maps to are the human-found omissions. The evaluator's labels are kept in a separate file so annotators work blind. `evaluation/agreement.py` reports κ on the label, agreement on the mapping, per-label precision and recall, dangerous misses, hallucinated items and omission recall. Full procedure: `docs/BENCHMARK.md`.

## 7. Limitations (known, measured in EXP-001)

1. **Lexical, not semantic.** v1.2 catches opposite words, quantifier and actor changes only for the words in its lists (§2.5, §2.6), and contradictions only when the draft step reuses the warning's verb and object words. Other meaning changes (for example "slowly" → "quickly", "any" → "most", or "raise the forks to inspect the chains" against "do not inspect the forklift with the forks raised") are not detected. The optional advisory semantic checker (`src/semantic_checker.py`, off by default) is the planned way to reach these. Correct paraphrases can be flagged as altered (`HARD-PARAPHRASE`, still a false alarm in v1.1, but one that errs on the safe side).
2. **Units only from a fixed list.** Unlisted units and single-letter units (m, g, l, s) are not compared. A number written without a unit in the source cannot be checked for a unit change.
3. **Structure-dependent.** Steps must be numbered lines. Tables, multi-column PDFs and scanned PDFs (no OCR) are not handled, and such cases produce `needs_review` findings rather than passes.
4. **Dependencies are approximated by source order.** Every pair of source steps is treated as order-critical, which over-flags harmless reorderings of independent steps.
5. **Synthetic validation set.** EXP-001 drafts were built with known edits, so it shows that each rule fires as designed. It does not show how often real LLM errors look like these edits. Real-world performance comes from EXP-002 with human annotation.
6. **Not a safety approval.** The framework cannot judge whether a requested change is itself safe.
