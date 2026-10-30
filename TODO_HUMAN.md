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
