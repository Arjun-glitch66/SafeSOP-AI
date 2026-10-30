# Decisions needed from a human

Items the coding agent stopped on because they need a product, licence, cost or labelling decision.

## Phase 0

- **0.4 Should "rejected" also be a final, locked state?** Right now only `approved` is locked
  (any later review gets HTTP 409). A `rejected` version can still be re-reviewed and even
  approved later. If rejection should be final, add `"rejected"` to `LOCKED_STATUSES` in
  `api.py` (one-line change). The test `test_approved_version_is_locked` shows the pattern.

- **0.6 Dead code that legacy/ still imports: not removed.** `src/document_parser.py` and the
  old evaluator functions at the top of `src/safety_evaluator.py` (`normalize_text`,
  `warning_recall`, `warning_precision`, `unsupported_instruction_rate`, `order_integrity`,
  `evaluate_sop`) are not used by the API, but `legacy/app.py` and `legacy/version_manager.py`
  import them, and legacy/ must not be touched. Choose one:
  1. Delete them, and accept that the archived Streamlit app no longer runs (README already
     says legacy/ is not used). Their tests in `tests/test_safety_evaluator.py` (first 6 tests)
     would be deleted too.
  2. Move them into `legacy/` (this edits legacy/, which the rules forbid without your OK).
  3. Keep them as they are.

## Phase 1

- **1.4 EXP-003: collect 30-50 public SOPs and run two-person labelling.** The code is ready
  (`evaluation/run_generation_experiment.py --sop-dir`, `evaluation/agreement.py`); the procedure
  is in `docs/BENCHMARK.md`. Needs you to:
  1. Collect the SOPs and check each one's licence. Decide whether the PDFs may be committed to
     the repo or must stay outside it (only `manifest.csv` committed).
  2. Write the change requests before seeing any draft.
  3. Approve the Gemini cost: manifest rows x models x repeats calls (about 80 for 40 requests,
     2 models, 1 repeat).
  4. Find two annotators who label independently (roughly 10 hours each for 80 drafts).
- **1.4 Second model from another provider?** `--models` compares Gemini models only; there is no
  provider interface yet. A non-Gemini generator needs a paid API key and an adapter in
  `src/sop_generator.py`. Decide whether EXP-003 needs one.
- **1.5 Semantic checker backends: licence, install size and data sharing.** `SEMANTIC_CHECK`
  stays `off` until you decide:
  - `nli`: default model `cross-encoder/nli-deberta-v3-small` (check its Hugging Face model card
    licence before use). Needs `pip install sentence-transformers`, which installs PyTorch
    (about 1-2 GB). Not added to `requirements.txt`. Runs locally.
  - `llm`: an Anthropic Claude judge (`SEMANTIC_LLM_MODEL`, default `claude-opus-5-5`). Needs
    `pip install anthropic` and an `ANTHROPIC_API_KEY`. Billed per evaluation, and it **sends the
    SOP warnings and draft steps to Anthropic**; check that this is allowed for your SOPs.
  - Neither backend has been evaluated. Run it on the EXP-003 labels before trusting it.

## Phase 2

- **2.4 Before anyone else uses it:** set `JWT_SECRET` (long random string) and
  `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env`, then create the author and reviewer accounts
  (`POST /api/users` from `/docs`). Decide whether you need password reset, account lockout or
  login rate limiting (not built; 3.4 only limits `/generate`).
- **2.2 Run prompt v3 once against the real Gemini API** (a few billed calls) to check that it
  fills `source_step_ids` / `source_warning_id` correctly. All tests use a stub.
