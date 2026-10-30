# Decisions needed from a human

Items the coding agent stopped on because they need a product, licence, cost or labelling decision.

## Phase 0

- **0.4 Should "rejected" also be a final, locked state?** Right now only `approved` is locked
  (any later review gets HTTP 409). A `rejected` version can still be re-reviewed and even
  approved later. If rejection should be final, add `"rejected"` to `LOCKED_STATUSES` in
  `api.py` (one-line change). The test `test_approved_version_is_locked` shows the pattern.
