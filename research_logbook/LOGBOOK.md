# SafeSOP AI — Research Logbook

Each entry records: date, experiment ID, source documents, simulated changes, prompt version, model settings, results, observed failures and next steps. Add new entries at the bottom and never rewrite old ones; if something turns out to be wrong, add a correction entry.

---

## Entry 0 — Baseline system milestones (before 2026-10-27)

- **Recorded by:** Arjun. Exact dates were not logged at the time.
- **What was shown working:** React/Vite frontend scaffold. FastAPI on port 8000. PDF upload and listing. Gemini connection test (`test_gemini.py`) returned SUCCESS. `POST /api/documents/{id}/generate`, called from Swagger, produced version 1 with a draft, change summary, preserved-warning claims, unresolved questions, model info, and a "not safety approved" warning.
- **Prompt:** first version of `build_sop_prompt` (later tagged `v1`).
- **Observed issues:** two incompatible SQLite schemas (`api.py` and `src/database.py`). The frontend was not connected to generation. The evaluator was not connected. `requirements.txt` was out of date.

## Entry 1 — Integration and schema consolidation (2026-10-27 to 2026-10-28)

- **Changes:**
  - The frontend now calls `/generate` and shows real version history and evaluation results.
  - `api.py` holds the single canonical schema. It is migrated additively, with an automatic backup.
  - Versions record source document, parent version, page, model, prompt version and tokens.
  - New tables `evaluations` and `review_history`.
  - The legacy Streamlit prototype is archived in `legacy/`.
- **Regeneration rule:** every generation, including a regeneration, reads the **original uploaded PDF**. `parent_version_id` records lineage only. Verified by an end-to-end test: the prompt for version 3 contained the original text, not version 2's draft, and the original PDF's SHA-256 was unchanged after three generations.
- **Tests:** 15 unit and migration tests pass (`pytest tests`). An end-to-end API check, with Gemini stubbed, passes.

## Entry 2 — EXP-001: evaluator validation on injected defects (2026-10-28)

- **Experiment ID:** EXP-001
- **Goal:** check that each rule of `safe-sop-eval-1.0` detects the failure type it was designed for, and record where it fails.
- **Source documents:** 4 synthetic SOPs written for this project (`evaluation/testset.json`): conveyor energy isolation, concentrated acid transfer, laboratory centrifuge, forklift pre-shift inspection. Each has 4 warnings and 8 steps.
- **Simulated changes:** one legitimate change request per SOP (e.g. flush volume 5 → 10 litres). Each is combined with 7 injected defects (missing warning, swapped steps, unsupported step, unsupported value, omitted step, duplicated step, negation flip), plus a clean variant and 1 hand-written hard case. That gives 36 cases.
- **Generator/model:** none. Drafts are built deterministically, so ground truth is exact.
- **Run:** `.venv\Scripts\python evaluation\validate_evaluator.py` → `results/evaluator_validation.md` / `.json`
- **Results:**

  | Metric | Value |
  |---|---|
  | Status accuracy | 0.917 (33/36) |
  | Defect cases flagged | 0.935 (29/31) |
  | False alarms on defect-free cases | 0.20 (1/5) |
  | Standard (non-hard) cases correct | 32/32 |
  | Per-type recall | 1.0 for missing_warning, omitted_step, step_order_violation, duplicated_step, unsupported_instruction; 0.8 for conflicting_instruction and unsupported_value |

- **Observed failures (all from hard cases, as predicted):**
  1. `SOP-CONV/HARD-ANTONYM`: "switch off" → "switch on" was **missed** (pass_automated). This is dangerous.
  2. `SOP-CENT/HARD-UNIT`: "3000 rpm" → "3000 rcf" was **missed**. This is dangerous.
  3. `SOP-ACID/HARD-PARAPHRASE`: a correctly paraphrased warning was flagged `altered_warning`, a false alarm that errs on the safe side.
- **Interpretation:** the rules work as designed on the defect types they target. The 32/32 on standard cases is expected by construction and is **not** evidence of real-world accuracy. The two misses show that lexical checks cannot catch meaning-changing edits that keep the same words.
- **Next steps:**
  - Add a unit-aware value check (number + unit pairs) and a small antonym list (on/off, open/close, raise/lower, before/after) as evaluator v1.1.
  - Re-run EXP-001 with new hard cases written **before** looking at v1.1's output, to avoid tuning to the test set.

## Entry 3 — EXP-002: real Gemini drafts (planned, not yet run)

- **Experiment ID:** EXP-002
- **Goal:** measure how often Gemini drafts lose warnings, invent instructions or values, or reorder steps, and measure the evaluator's agreement with human labels.
- **Source documents:** the 4 SOPs from EXP-001. Add public SOPs (e.g. OSHA or university lab SOPs, with their sources cited) in the same JSON format when available.
- **Simulated changes:** the legitimate change request of each SOP.
- **Model settings:** `GEMINI_MODEL` from `.env` (record the exact model ID here when run). Default temperature. Prompt `v1`. Full-document scope.
- **Run:** `.venv\Scripts\python evaluation\run_generation_experiment.py --repeats 3` (needs a Gemini API key in `.env`)
- **Outputs:** `results/EXP-002_generation.md` (summary), `results/EXP-002_annotation.csv` (to be labelled by a human following framework §6), `results/raw/EXP-002/` (full responses, gitignored).
- **Results:** *not run yet. Fill in after running.*
- **Then:** two people label the annotation CSV independently. Report the evaluator's accuracy against the human labels and its recall of human-labelled `missing` items.

## Entry 4 — EXP-001b: evaluator v1.1 against held-out hard cases (2026-10-29)

- **Experiment ID:** EXP-001b (same runner as EXP-001, with an expanded test set)
- **Goal:** fix the two dangerous misses from EXP-001 (opposite words, unit changes) without tuning to the test set.
- **Procedure (order matters):**
  1. Six new **held-out** hard cases were written **before** any v1.1 code existed (group `hard-heldout` in `evaluation/testset.json`): tighten→loosen, lower→raise, after→before, 10 litres→10 millilitres, 0.1 grams→0.1 kilograms, and a negative control (clauses reordered, same meaning, which must *not* be flagged). The four EXP-001 hard cases became group `hard-dev`.
  2. v1.0 was run on all 42 cases as a baseline: `results/evaluator_validation_safe-sop-eval-1.0.md`.
  3. v1.1 was implemented (framework §2.4 unit check and §2.5 opposite-word list) and run on the same 42 cases: `results/evaluator_validation_safe-sop-eval-1.1.md`.
- **Results:**

  | Group | v1.0 correct | v1.1 correct |
  |---|---|---|
  | standard (32) | 32 | 32 |
  | hard-dev (4) | 1 | 3 |
  | hard-heldout (6) | 1 (the negative control) | **6** |
  | **All 42: status accuracy** | 0.810 | **0.976** |
  | Defect cases flagged | 0.806 | **1.000** |
  | False alarms on defect-free cases | 0.167 | 0.167 |

  Figure: `results/charts/exp001_accuracy_by_group.svg`
- **Remaining failure:** `SOP-ACID/HARD-PARAPHRASE`, a correct paraphrase flagged `altered_warning`. This is a false alarm on the safe side; it was not changed, because word overlap cannot recognise synonyms.
- **Caveat (important for interpreting 6/6):** the held-out cases were written by the same team that wrote v1.1, and they knew which *categories* v1.1 would target (opposite words, units). They test generalisation to new word pairs and units within those categories, not to new kinds of error. EXP-002 with human labels remains the real-world test.
- **Post-review fixes, before finalising v1.1:** the code review found that (a) two source steps merged into one draft step were counted as an order reversal, and (b) "celsius" was cut to "celsiu" by the plural strip, so °C/°F changes were never compared. Both were fixed and covered by tests. EXP-001b was re-run and the numbers above are unchanged.

## Entry 5 — System v1.2: generation, review workflow, UI and QA (2026-10-29)

- **Generation (prompt v2):**
  - Gemini returns JSON enforced by a response schema (`SopDraft` in `src/sop_generator.py`), rendered into the same section layout as v1.
  - Temperature 0.2 by default (`GEMINI_TEMPERATURE` overrides it).
  - SDK retries with backoff on 429/5xx, and a 120 s timeout.
  - Each version records temperature and output mode.
  - A response that is not a complete structured draft (e.g. cut off at MAX_TOKENS) is now **rejected, and no version is saved**, instead of storing a JSON fragment.
- **API:**
  - `GET /api/versions/{id}/diff`: line diff of the original against the draft section.
  - `GET /api/versions/{id}/download?format=pdf`: a labelled text PDF, not the original layout.
  - `page_count` is stored at upload, and uploads must open as PDFs.
  - Reviews require a reviewer name. **Approving a version whose latest automated check is not `pass_automated` requires a written justification, enforced by the server** (before, only the UI asked for confirmation).
  - The migration backfills `source_document_id` on every start.
  - `lifespan` replaces the deprecated `on_event`.
- **Frontend:**
  - `App.jsx` (≈650 lines) split into `pages/` and `components/`.
  - Side-by-side diff with source warnings marked.
  - PDF download.
  - Progress state during generation, and a page-range check.
  - Responses that arrive after the user has moved on to another document or version are ignored.
  - Placeholder controls removed (search/⌘K, bell, settings, profile, workspace menu).
  - Accessibility: 86 font sizes raised (body text ≥ 12px), 79 text colours darkened to WCAG AA 4.5:1, labelled form fields, radio roles, keyboard-reachable table rows.
- **Testing:**
  - 38 pytest tests (API end-to-end with Gemini stubbed, migration, evaluator, generator, agreement).
  - GitHub Actions CI (`.github/workflows/ci.yml`) runs the tests, EXP-001 and the frontend build.
  - A full browser QA run (upload → generate → evaluate → diff → review → regenerate → PDF), using a stand-in generator because there was no API key. No console errors; the layout works at 375 px wide.
- **Code review:** 10 findings, all confirmed and fixed (2 in the evaluator, 4 in the API/generator, 4 in the frontend). Listed in the session notes and reflected in the tests.
- **Security review (manual):**
  - Uploads are validated by extension, signature and parse. Stored names are UUIDs.
  - All SQL is parameterised. All rendered model text is escaped. CORS is limited to localhost.
  - The key is never logged or returned.
  - **Open risk:** there are no user accounts, so anyone who can reach the local API can record a review. Acceptable for a local prototype; it must not be deployed on a shared network as is.

## Entry 6 — Corrections and changes to earlier entries (2026-10-29)

- Entry 2's report file was renamed to `results/evaluator_validation_safe-sop-eval-1.0.md`. That file now holds v1.0 run on the **42-case** set (Entry 4). Entry 2's numbers (36 cases: status accuracy 0.917) describe the earlier 36-case run, which is not kept as a separate file.
- Entry 3 (EXP-002) still applies, with two changes: drafts are now generated with **prompt v2** (JSON output, temperature 0.2), and the annotation CSV has two columns (`human_label_a`, `human_label_b`) for independent annotation. After labelling, run `evaluation/agreement.py results/EXP-002_annotation.csv`.

## Entry 7 — EXP-002 run: real Gemini drafts, automated part (2026-10-29)

- **Experiment ID:** EXP-002 (planned in entry 3; settings updated in entry 6)
- **Model settings:** `gemini-3.5-flash-lite` (`gemini-2.5-flash-lite` returned 404 "no longer available to new users", so the project default was changed), prompt `v2` (JSON schema), temperature 0.2. Evaluator `safe-sop-eval-1.1`.
- **Source documents and changes:** the 4 test-set SOPs, each with its legitimate change request, 3 runs each.
- **Run:** `evaluation/run_generation_experiment.py --repeats 3`, started 2026-10-29 12:28 UTC → `results/EXP-002_generation.md`. Raw responses are in `results/raw/EXP-002/` (gitignored).
- **Results (automated):** 12/12 calls succeeded, all with structured output. All 12 drafts were `pass_automated`: warning recall 1.0, step coverage 1.0, order integrity 1.0 and unsupported-instruction rate 0.0 in every run. The only findings were `altered_step` (info), which is the requested change itself.
- **Manual check, outside the evaluator:** each draft was searched for the change's key terms (e.g. "10 litres", "ethanol", "digital"). **All 12 applied the requested change.** The evaluator does not check this today: a draft that ignored the change request would also pass.
- **Interpretation:** on short, cleanly structured SOPs (8 steps, 4 warnings), Gemini at temperature 0.2 made no errors the framework can detect, consistently across 3 runs. This is a **ceiling effect**. It shows the pipeline works with a real model, but it cannot measure how well the evaluator catches real model errors, because none occurred.
- **Still to do:**
  1. Human annotation of `results/EXP-002_annotation.csv` by two annotators (144 rows), then `evaluation/agreement.py`.
  2. **EXP-003 (proposed):** harder inputs to provoke real errors. Longer, multi-page public SOPs; change requests that touch several steps, conflict with a warning, or are ambiguous; page-scoped requests.
  3. Add a **change-application check** to the evaluator (do the change request's new values and terms appear in the draft?) as v1.2, with test cases written first.

## Entry 8 — Phase 0: quick fixes (2026-10-30)

Engineering only; no experiment was run and the evaluator (`safe-sop-eval-1.1`) is unchanged.

- **Test hygiene:** the Gemini connection check moved from `test_gemini.py` to `scripts/check_gemini.py`; `pytest.ini` sets `testpaths = tests`, so a bare `pytest` can no longer make a billed call.
- **Version-number race:** two concurrent generations could both read the same `MAX(version_number) + 1` and the second insert failed *after* Gemini had been paid. A test with 8 threads reproduced it (UNIQUE constraint error → HTTP 500). Numbering and insert now run inside `BEGIN IMMEDIATE`; the existing `UNIQUE(document_id, version_number)` stays as the backstop, with a retry.
- **Limits before the model call:** 50 pages (full scope), 60k extracted characters, 2,000-character change requests and review comments, 100-character reviewer names.
- **Review states:** approved versions are locked (409 on any later review). Whether `rejected` should also be final is open (TODO_HUMAN.md).
- **Change requests:** `target_page` is now its own column (added by the migration; old rows keep `NULL`), and `/generate` accepts `request_id` to draft from a saved request.
- **Dead code:** removed the unused `data/versions/*.md` writes, Tailwind (only its CSS reset was used; the needed parts now live in `index.css`), `icons.svg` and `getChangeRequests`. `src/document_parser.py` and the old evaluator functions were **kept** because `legacy/` imports them (TODO_HUMAN.md).
- **Accessibility:** inert closed mobile nav, `+`/`−` diff markers with screen-reader text, ≥ 3:1 control borders, one `h1` and a `document.title` per view, full ARIA tab pattern on the version view, error boundary per view, toast timer fix, backend health polled every 15 s.
- **Config:** CORS origins come from `ALLOWED_ORIGINS`.
- **Verification:** 47 pytest tests pass (38 → 47); frontend build passes; a headless-browser check at 1440 px and 375 px showed the layout unchanged after removing Tailwind, and `inert`/`aria-expanded` switching correctly on the mobile nav.

## Entry 9 — Phase 1: evaluator v1.2, EXP-001c, benchmark scaffolding, advisory semantic check (2026-10-30)

- **Motivation:** four known v1.1 failures, all `pass_automated` with no findings: (A) an inserted step "Bypass the emergency stop circuit to verify the conveyor." against "DANGER: Do not bypass the emergency stop circuit"; (B) "after all personnel are clear" → "after most" (`all` was a stop-word); (C) a draft identical to the original (change ignored); (D) "each worker must apply a personal lock" → "the supervisor must apply a single lock" (only `needs_review`).
- **Test set v2 (written first):** 22 new hard cases. A–D are `hard-dev`, because they defined the rules. 18 `hard-heldout` cases were written before any v1.2 code: contradicting inserted steps (5), quantifier weakening (3), an actor change, a timing change, ignored or dropped change requests (4), and 5 should-pass cases. The held-out cases are by the same author as the rules, so they are held out from tuning only. They were not looked at while developing v1.2.
- **Before (v1.1, 64 cases):** status accuracy 0.734; hard-dev 3/8; hard-heldout 12/24; false alarms 1/11 (the known HARD-PARAPHRASE). `results/evaluator_validation_safe-sop-eval-1.1_testset-v2.md`.
- **Evaluator v1.2:** `contradicts_warning` (every draft step vs every source prohibition: verb + object + condition), `quantifier_weakened`, `actor_changed` (new `high` severity, fails like critical), `change_not_applied`; `all/any/each/before/after` are no longer stop-words; new findings quote evidence with line numbers.
- **After (v1.2, same 64 cases, EXP-001c):** status accuracy 0.938; hard-dev 7/8; hard-heldout 21/24; standard 32/32; false alarms unchanged at 1/11 and 0/6 on held-out should-pass cases. Held-out recall: `contradicts_warning` 4/5, `quantifier_weakened` 2/3, `change_not_applied` 2/3, `actor_changed` 1/1, with 95% case-bootstrap intervals in `results/evaluator_validation_safe-sop-eval-1.2.md` (too narrow, because cases share 4 SOPs).
- **Held-out misses, left unfixed so the held-out number stays honest:** "raise the forks … to inspect the chains" (object differs from the warning's "forklift"); "any" → "most" ("any" is not in the strong list); dropped "10 litres" where "10" already appears elsewhere in the original. Fixing these needs new held-out cases written first.
- **EXP-003 scaffolding:** `run_generation_experiment.py --sop-dir --models`; annotation redesigned to one row per draft item (`supported / unsupported / contradicting` + source-item mapping), with evaluator labels in a separate file so labelling is blind; `agreement.py` computes κ, mapping agreement, per-label precision/recall, hallucinations and omission recall. Procedure: `docs/BENCHMARK.md`. Collecting SOPs and two-person labelling are open (TODO_HUMAN.md).
- **Advisory semantic check:** `src/semantic_checker.py`, NLI cross-encoder or Anthropic LLM judge, behind `SEMANTIC_CHECK` (default off, off in CI). Adds advisory findings only, raises at most to `needs_review`, never lowers a status. Tested with fakes only; not evaluated.
- **Not measured yet:** any real-model accuracy of v1.2, κ, the semantic checker's precision/recall.
- **Tests:** 47 → 74.
