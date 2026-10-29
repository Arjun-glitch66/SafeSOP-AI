# SafeSOP AI: Generative AI for Automated SOP Revision with Safety-Critical Evaluation

**Tier 4 Capstone · Draft report**

Status: complete except the human-annotation rows of Section 5.3 (EXP-002), which are marked *pending*.

---

## Abstract

Standard Operating Procedures (SOPs) are updated by hand, so documentation lags behind process changes. SafeSOP AI drafts a revised SOP from an existing PDF and an engineer's change request using Google Gemini, then checks the draft automatically against the unchanged original for safety-critical failures. The checks are lost warnings, invented instructions or values, reordered steps, and omitted, duplicated or contradicted steps. Every draft is stored as a separate version with its lineage, model settings, automated evaluation and human review decision. We define an original rule-based evaluation framework (SAFE-SOP) with explicit metrics, thresholds and uncertainty rules, and validate it on 42 constructed cases. Version 1.1 handles all 32 standard defects and all 6 held-out hard cases correctly, with one false alarm on the safe side. The automated checks never approve a draft: approval is a recorded human decision.

## 1. Problem and objectives

**Problem.** SOP revisions are manual, slow and error-prone. An LLM can draft revisions quickly, but in safety-critical procedures a fluent draft that silently drops a warning, changes a value or reorders an isolation step is dangerous.

**Objectives.**
1. Draft revised SOPs from an existing PDF plus a process-change request.
2. Never modify the original. Always regenerate from the original, not from earlier drafts.
3. Detect, automatically and measurably, the failure types that matter for safety.
4. Keep a complete, auditable revision history, with human review separate from automated checks.

## 2. System design

```mermaid
flowchart LR
    UI["React + Vite UI"] -->|REST| API["FastAPI"]
    API --> GEN["Generator (prompt v2)"] -->|JSON schema| GEM[("Gemini")]
    API --> EVAL["SAFE-SOP evaluator v1.1"]
    API --> DB[("SQLite: documents, change_requests,<br/>versions, evaluations, review_history")]
    API --> FILES[("Immutable original PDFs")]
```

- **Immutability.** Uploads are stored as `<uuid>.pdf` with their SHA-256 and are never written to again. An automated test confirms the hash is unchanged after several generations.
- **Regeneration rule.** Each generation reads the *original* PDF (the full document or one page). Regenerating from version *n* records `parent_version_id = n` for lineage only; version *n*'s text is never used as the source. This prevents errors compounding across revisions.
- **Generation.** The prompt (v2) treats the source as the authority, forbids invented facts, requires warnings and step order to be preserved, and asks the model to flag uncertainty. Output is a JSON object enforced by a response schema. Temperature is 0.2. The client retries rate-limit and server errors. Incomplete output is rejected, and no version is created.
- **Traceability.** Every version records its source document, parent, change request, scope or page, model, prompt version, temperature, token counts and time. Evaluations and reviews are append-only tables.
- **Human review.** A reviewer approves, rejects or requests revision. Approval needs a name, and if the automated checks did not pass, a written justification enforced by the server.

## 3. SAFE-SOP evaluation framework

The full definitions are in `research_logbook/EVALUATION_FRAMEWORK.md`. In summary:

| Check | Metric | Severity |
|---|---|---|
| Warning preservation | Warning recall = preserved / source warnings (token containment ≥ 0.8; 0.5–0.8 counts as *altered*) | missing = critical, altered = review |
| Unsupported instructions | Rate of draft steps not supported by the source and the change request (support < 0.5) | critical |
| Unsupported values | Numbers absent from the source and the change request; known numbers with a different unit | critical |
| Step-order integrity | Share of source step pairs kept in order (pairwise concordance) | any inversion = critical |
| Omitted, altered, duplicated, conflicting steps | Step mapping by Dice similarity; negation flips; opposite-word list | critical / review |
| Uncertain cases | Borderline scores or undetectable structure | always `needs_review`, never a pass |

**Decision rule:** any critical finding → `fail`; else any review finding → `needs_review`; else `pass_automated` ("no rule fired", **not** approval). The model's own claims about which warnings it preserved are ignored.

## 4. Experimental setup

| ID | Data | Generator | Ground truth |
|---|---|---|---|
| EXP-001 / 001b | 4 synthetic SOPs written for this project (conveyor isolation, acid transfer, centrifuge, forklift inspection), each with 4 warnings and 8 steps, plus 1 legitimate change request each | None: drafts built by known edits | Exact (the edits are known) |
| EXP-002 | The same 4 SOPs and change requests, 3 runs each | Gemini, prompt v2, temperature 0.2 | Two independent human annotators (framework §6) |

EXP-001 cases: for each SOP, 1 clean draft and 7 drafts with one injected defect each (missing warning, swapped steps, unsupported step, unsupported value, omitted step, duplicated step, negation flip). On top of these: 4 hard cases known while designing v1.1 (`hard-dev`), and 6 hard cases written before v1.1 existed (`hard-heldout`), including one negative control. 42 cases in total.

## 5. Results

### 5.1 EXP-001b: evaluator validation (v1.0 vs v1.1, same 42 cases)

![Cases handled correctly by case group](../results/charts/exp001_accuracy_by_group.svg)

| Group | v1.0 | v1.1 |
|---|---|---|
| Standard defects (32) | 32/32 | 32/32 |
| Hard, dev (4) | 1/4 | 3/4 |
| Hard, held-out (6) | 1/6 | 6/6 |
| Status accuracy (all 42) | 0.810 | 0.976 |
| Defect cases flagged | 0.806 | 1.000 |
| False alarms on defect-free cases | 0.167 | 0.167 |

Per finding type (v1.1), recall is 1.0 for every type: missing warning, omitted step, step-order violation, duplicated step, unsupported instruction, unsupported value and conflicting instruction. The only error is one false positive (`altered_warning` on a correct paraphrase). Full tables: `results/evaluator_validation_safe-sop-eval-1.1.md`.

### 5.2 What the misses taught us

v1.0 missed "switch off" → "switch on" and "3000 rpm" → "3000 rcf". Both are dangerous, and both keep almost every word, so overlap-based checks cannot see them. v1.1 adds an explicit opposite-word list and a number-plus-unit comparison.

### 5.3 EXP-002: real Gemini drafts

Model `gemini-3.5-flash-lite`, prompt v2 (JSON schema), temperature 0.2; 4 SOPs × 3 runs.

| Measure | Value |
|---|---|
| Successful generations | 12 / 12 (all structured output) |
| Status: fail / needs_review / pass_automated | 0 / 0 / 12 |
| Mean warning recall · step coverage · order integrity | 1.0 · 1.0 · 1.0 |
| Mean unsupported-instruction rate | 0.0 |
| Drafts that applied the requested change (manual check) | 12 / 12 |
| Cohen's κ between annotators | *pending human annotation* |
| Evaluator problem recall vs. humans | *pending human annotation* |
| Dangerous misses | *pending human annotation* |

On these short, well-structured SOPs, Gemini made no errors the framework detects, consistently across runs. This is a ceiling effect: it shows the pipeline works end to end with a real model, but not how well the evaluator catches real errors. The proposed EXP-003 uses harder inputs (longer public SOPs, multi-step or conflicting change requests) to provoke them. The evaluator also does not yet verify that the requested change was applied; this was checked by hand here.

## 6. Discussion and limitations

- **The validation set is synthetic.** The standard-case scores show the rules work as designed; they are expected by construction. The held-out set was written by the same team, who knew the target categories (opposite words, units), so 6/6 shows generalisation within those categories, not to new kinds of error. Real-world accuracy comes from EXP-002.
- **Words, not meaning.** Paraphrases can raise false alarms. Meaning changes that keep the same words, beyond the fixed opposite-word list, are missed.
- **Structure-dependent.** Steps must be numbered lines. Tables, multi-column layouts and scanned PDFs (no OCR) are not handled; they produce `needs_review`, not a pass.
- **Order approximation.** Every source step pair is treated as order-critical, which over-flags harmless reorderings.
- **Prototype security.** There are no user accounts; the system is intended for localhost use. Uploads are validated, SQL is parameterised, model output is escaped, and the API key is never logged.
- **No safety approval.** The framework cannot judge whether the requested change itself is safe.

## 7. Future work

1. An advisory semantic check (an LLM comparing meaning), measured against the human labels and never used for approval.
2. Explicit dependency annotation (which steps must precede which), instead of treating all source order as critical.
3. OCR and table extraction. Section- and step-scoped revision.
4. Authenticated reviewers with roles.

## 8. Reproducibility

```
.venv\Scripts\python -m pytest -q tests
.venv\Scripts\python evaluation\validate_evaluator.py
.venv\Scripts\python evaluation\make_charts.py
.venv\Scripts\python evaluation\run_generation_experiment.py --repeats 3
.venv\Scripts\python evaluation\agreement.py results\EXP-002_annotation.csv
```

Dependency versions are pinned in `requirements.txt`. CI runs the tests and EXP-001 on every push. The research logbook (`research_logbook/LOGBOOK.md`) records every experiment, with dates and settings.
