# SafeSOP AI — Project Completion Audit

- **Repository audited:** `SafeSOP-AI-Updated` (branch `main`, commit `78033ce`, clean working tree at start)
- **Audit date:** 2026-11-06
- **Method:** every claim in the README and logbook was traced to code. Every gate in CI was run locally.
  Nothing below is marked "tested" unless a test in this repository runs it.

Section 9 (at the end) records what was changed after this audit and the results after the changes.
Sections 1 to 8 describe the repository **as found**.

## 0. Baseline (as found, before any change)

| Gate | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` | **153 passed, 1 failed** (`test_only_approved_versions_export_and_the_export_carries_the_signature`) |
| Lint | `ruff check .` | passed |
| Types | `mypy` (lenient, `app/` + `src/`) | passed, 34 files |
| Python CVEs | `pip-audit -r requirements.txt` | no known vulnerabilities |
| Evaluator validation (EXP-001c) | `python evaluation/validate_evaluator.py` | 64 cases, status accuracy 0.938, defects flagged 0.943, clean false alarms 0.091. **Identical to the committed results** (only date and commit changed), so the experiment reproduces. |
| Frontend lint | `npm run lint` | passed |
| Frontend tests | `npm test` | 5 passed (1 file) |
| Frontend build | `npm run build` | passed (JS 324 kB, 101 kB gzip) |
| JS CVEs | `npm audit --omit=dev` | 0 vulnerabilities |
| Live Gemini call | `python scripts/check_gemini.py` | **not run: no `.env` in this repository** (no key available) |
| Docker / Postgres / Tesseract | — | **not available on this machine**; not run (the previous phase reported the same) |

Environment: Windows 11, Python 3.14.8 (shared `.venv` one folder up), Node 24.21, npm 11.19.
`frontend/node_modules` and the dev tools (`ruff`, `mypy`, `pip-audit`, `pytest-cov`) were not installed and
were installed from the lockfile / `requirements-dev.txt` for this audit.

### Root cause of the failing test (a real defect, not a flaky test)

The approved-version PDF export renders SHA-256 fingerprints in a proportional font. PyMuPDF's
layout engine applies typographic ligatures, so `...bedff0913...` is written with the single glyph
`ﬀ` (U+FB00) and "qualified" with `ﬁ`. Text copied or extracted from the controlled document then
contains a hash **that does not verify**. The test only fails when a hash happens to contain `ff`, `fi`
or `fl`, which is why it passed before. Fix: render fingerprints and ids in a monospace font
(verified: no ligatures in monospace).

## 1. Feature classification

Legend — **IT**: implemented and tested · **IU**: implemented, not tested · **P**: partial ·
**NI**: not implemented · **B**: broken / needs correction.

### Backend and workflow

| Feature | Status | Evidence / note |
|---|---|---|
| PDF upload (size limit, magic bytes, empty file, SHA-256, immutable storage) | IT | `app/routers/documents.py`, `tests/test_api.py` |
| Encrypted / password-protected PDF at upload | **B** | Opens, then text extraction yields nothing; the user only finds out at generation. Should be rejected at upload with a clear message. |
| PDF text extraction with `[PAGE n]` markers, page limit, char limit | IT | `app/services/pdf.py` |
| OCR fallback for scanned pages | IU (mocked) | Tesseract not installed; tested with a mock only. |
| Gemini generation, structured JSON (pydantic schema), prompt v4 | IT (stubbed) | Never run against the live API in this repo (no key). |
| Retry handling | P | Transport errors (429/5xx) are retried by the SDK. A truncated or invalid structured response is **not** retried on the primary provider; it fails or goes straight to the fallback. |
| LLM fallback provider (Ollama) | IT (stubbed) | |
| Prompt-injection hardening (system instruction, random boundaries) | IT | `tests/test_sop_generator.py` |
| Reason for every proposed modification | **NI** | Steps carry `change_type` and source ids, but no per-change reason. Only a free-text `change_summary`. Requirement §4 is not met. |
| Distinguish original vs modified content | P | The diff view shows it; the stored draft text and exports do not mark which steps changed. |
| Full, page, section and step scope | IT | |
| Background jobs + SSE progress | IT | In-process thread pool (single API process). |
| Version creation, numbering under concurrency, lineage | IT | |
| Re-run evaluation (`POST /versions/{id}/evaluate`) | **B** for section/step scope | Stored `structured_json` for section/step drafts holds ids local to the revised part (S1 = first step *of the part*), but the re-run compares it against the **whole** document by id. Findings after a re-run are wrong (steps reported omitted / misattributed). Generation itself handles this correctly. |
| Review decisions, e-signature (password re-entry), separation of duties, approval lock | IT | |
| "Rejected" as a final state | Decision pending | TODO_HUMAN 0.4 — left for the owner. |
| Role-based access control (author / reviewer / admin) | IT | Every router except health requires sign-in; write endpoints check roles. |
| User management | P | API create + list only. No role change, no password reset, no change-own-password, no UI. |
| Login throttling / lockout | **NI** | Unlimited password guessing against `/api/auth/login` and the approval signature. |
| Hash-chained, append-only audit log + verification | IT | API only; no UI to view or verify. |
| Exports: approved DOCX/PDF, draft PDF/TXT, evaluation report PDF | **B** (PDF hashes) | See root cause above. DOCX is correct. |
| Alembic migrations, pre-Alembic upgrade with backup | IT | `tests/test_migration.py` (SQLite only). |
| Postgres support | IU | DDL generated offline only. |
| Health / readiness | IT | |
| Rate limit + daily quota on `/generate` | IT | |

### AI evaluation (SAFE-SOP evaluator v1.3)

| Metric requested | Status | Note |
|---|---|---|
| Warning recall (strict + lenient) | IT | |
| Warning precision | **NI** in the evaluator | Exists only in the legacy label-based functions. |
| Unsupported instruction rate | IT | |
| Procedure order integrity | IT | |
| Safety-constraint preservation (prohibitions, required elements, hierarchy of controls) | IT | |
| Semantic consistency | P | Word-overlap only. Optional NLI/LLM checker exists, off by default, never evaluated. No lexical consistency metric is reported. |
| Duplicate instructions | IT | |
| Contradictory instructions (negation, antonyms, warning contradictions) | IT | |
| Changed quantities and measurements | **P** | New numbers and unit swaps are caught. A value changed to **another number that already occurs elsewhere in the source** (e.g. "wait 5 minutes" → "wait 10 minutes" when "10" appears in another step) is **not** caught. |
| Changed responsible persons | P | Only on lock / tag / verify / permit steps, by word list. |
| Missing or weakened warnings | **P** | Missing, altered, negated and quantifier-weakened warnings are caught. A **signal-word downgrade** (DANGER → CAUTION, WARNING → NOTE) is not detected: the label words are stop-words, so the line still "matches". |
| Unexplained changes | NI | Needs the per-change reason (above). |
| Human annotation of findings | IT | Per-finding true/false-alarm verdicts, export script, Cohen's kappa script. |
| Baseline comparison | **NI** | No comparison of the evaluator with simpler baselines on the labelled test set. |
| Real-model results with human labels | P | EXP-002: 12 real Gemini drafts, automated part only; the human label columns are empty. EXP-003 not run (needs SOPs, annotators, budget). |

### Frontend

| Area | Status | Note |
|---|---|---|
| Sign-in, session expiry handling | IT (partly) | |
| Dashboard / overview | **NI** | The app opens on the document list. |
| Document list, search, upload (drag-and-drop, SOP type) | IU | Only components are unit-tested. |
| Revision studio (scope, section/step picker, translation, save-only, regenerate) | IU | |
| Generation progress (SSE, stop watching) | IU | |
| Preview, side-by-side diff, version-vs-version, original PDF preview | IU | |
| Safety metrics and findings, "show in comparison", finding verdicts | IU / IT | `EvaluationReport` has component tests. |
| Per-change reasons ("what changed and why") | NI | |
| Version register | **B** (minor) | Section- and step-scoped drafts are labelled "Full document". |
| Review page + sign-off dialog | IT (dialog) | |
| User and role management UI | **NI** | Admins must use `/docs`. |
| Audit log viewer / chain verification UI | **NI** | |
| Change own password | NI | |
| Exports and downloads | IU | |
| Error, loading, empty states | IU | Present on all pages read. |

## 2. Issues by category

Severity: **Critical** (wrong safety result or broken controlled record) · **High** (security or a
requirement not met) · **Medium** (incorrect behaviour with a workaround) · **Low** (polish).

| # | Category | Issue | Severity | Impact | Recommended fix |
|---|---|---|---|---|---|
| 1 | Backend bug | PDF export hash ligatures (§0) | **Critical** | An approved controlled document carries a fingerprint that does not verify when copied | Monospace rendering for hashes and ids |
| 2 | Backend bug | Re-run evaluation of section/step drafts uses part-local ids against the whole document | **Critical** | Wrong findings shown to a reviewer after "Re-run checks" | Use the text path for section/step scope, as generation does |
| 3 | Evaluation | Signal-word downgrade (DANGER → CAUTION) not detected | **High** | A weakened hazard warning passes as "preserved" | New `warning_downgraded` rule |
| 4 | Evaluation | Value changed to a number found elsewhere in the source **with the same unit (or unitless)** is not detected. *Corrected during Phase 4: as first written this row was broader; a reused number with a different unit is already caught by the v1.1 unit check.* | **High** | "Wait 30 min" → "wait 10 min" (10 min used elsewhere) passes silently | New `value_changed` rule on matched pairs |
| 5 | AI pipeline | No reason per modification; no unexplained-change check | **High** | Requirement §4 not met; reviewers cannot see why a step changed | Prompt v5: `reason` on steps and warnings; `unexplained_change` finding; change log in the draft and UI |
| 6 | AI pipeline | No retry on truncated / invalid structured output | Medium | One bad response fails the job (or uses the fallback) | One retry on the primary for invalid output before the fallback |
| 7 | Evaluation | Warning precision and a consistency score are not reported | Medium | Requested metrics missing | Add `warning_precision` and `lexical_consistency` (documented as lexical, not semantic) |
| 8 | Evaluation | No baseline comparison | Medium | The evaluator's added value is not shown | Baselines on the same labelled cases |
| 9 | Security | No login throttling; the approval password can also be guessed | **High** | Online password guessing | Per-username and per-client failure limit with 429 + Retry-After, also on the approval signature |
| 10 | Security | No password change / reset, no role change | Medium | Compromised or forgotten passwords need DB edits | Admin role change and password reset (audited); change-own-password |
| 11 | Backend | Encrypted PDFs accepted at upload | Medium | Confusing failure later | 400 at upload |
| 12 | Frontend | No dashboard, user management, audit viewer | Medium | Requirement §6 not met; admins need `/docs` | Add the three pages using existing endpoints plus a summary endpoint |
| 13 | Frontend | Register mislabels section/step scope | Low | Misleading list | Label all four scopes |
| 14 | Frontend | Checks page does not list the new rules | Low | Docs drift | Update with the evaluator |
| 15 | Security | Audit log readable only by admin, but `/api/audit/verify` open to every signed-in user | Low (by design) | Only reveals counts and a hash | Keep; documented |
| 16 | Security | Token stored in `localStorage` | Low / accepted | XSS would expose the token; no third-party scripts and React escaping limit this | Documented; httpOnly cookies are a future option |
| 17 | Security | Documents are visible to every signed-in user (no per-document ACL) | Low (single-organisation design) | — | Documented as a deployment assumption |
| 18 | Deployment | Jobs and the per-minute limit are in-process | Medium | Must run one API process | Documented (already); Redis/Postgres queue is future work |
| 19 | Deployment | Docker, Postgres and OCR never executed | Medium | Unverified paths | Owner to run once (TODO_HUMAN) |
| 20 | Licence | PyMuPDF is AGPL-3.0 | Decision | Network deployment obligations | Owner decision (TODO_HUMAN) |
| 21 | Gemini | No live call verified in this repository | Medium | Integration verified with stubs only | Owner runs `scripts/check_gemini.py` with a local `.env` |
| 22 | Academic | EXP-002 human labels empty; EXP-003 not run | **High** for the capstone | No human-validated result on real model output | Owner + second annotator label `results/EXP-002_annotation.csv`; the tooling is ready |
| 23 | Tests | No tests for login throttling, user admin, overview, section-scope re-evaluation, encrypted upload | Medium | — | Added with the fixes |

**Not found** (checked): secrets in the repository or git history of tracked files (`.env` is ignored and absent;
`.env.example` has empty values only); SQL built from user input (all user values are bound parameters; the
only f-string SQL uses constant column names); path traversal on upload (the stored name is a UUID); HTML injection in
PDF/DOCX exports (all values escaped).

## 3. Security review summary

| Area | Finding |
|---|---|
| Secrets | `.env`, `.env.*` (except `.env.example`), `data/`, `*.db`, `results/raw/`, `node_modules/`, `dist/`, `.venv/` are ignored. No credentials in frontend code (the frontend only knows `VITE_API_BASE`). |
| Authentication | bcrypt (12 rounds), HS256 JWT with expiry, user re-read on every request, constant-work login for unknown users. Missing: throttling (#9), password change (#10). Warns at startup when `JWT_SECRET` is missing or short. |
| Authorisation | Router-level sign-in on all data endpoints; role checks on writes; separation of duties and approval lock enforced on the server. |
| File upload | Size streamed and capped, magic bytes, parse check, UUID file names, original never modified. Missing: encrypted PDF check (#11). |
| Prompt injection | Rules in the system instruction, untrusted text in per-request random boundaries, output constrained to a schema; the evaluator never trusts the model's claims (an "unchanged" step is still compared). Residual risk: a model can still be steered; the evaluator and the human review are the controls. |
| Audit integrity | Hash chain, SQLite triggers refusing UPDATE/DELETE, write lock to serialise the chain head, verification endpoint. A DB superuser can still rewrite the whole chain consistently; an external anchor (e.g. periodically publishing the head hash) is future work. |
| Dependencies | pip-audit and npm audit clean on 2026-11-06. Licences: PyMuPDF AGPL-3.0 (decision pending); others permissive (MIT/BSD/Apache). |

## 4. Prioritised plan

| Phase | Work |
|---|---|
| 3 Backend | #1 export fix · #2 re-evaluation fix · #11 encrypted PDF · #9 login + signature throttling · #10 user admin + change password · overview endpoint for the dashboard |
| 4 AI + evaluation | #5 prompt v5 reasons + change log · #6 output retry · evaluator v1.4: #3, #4, #7, unexplained change · new labelled cases · re-run EXP-001 · #8 baselines |
| 5 Frontend | Dashboard · users · audit log · change password · change log with reasons · #13 · #14 · tests |
| 6 Verification | All gates again; live API smoke test of the started server; security re-check |
| 7 Docs | Architecture, DB schema, API, AI pipeline, evaluation (definitions, formulas, limitations), security, deployment; logbook entry; TODO_HUMAN |

Decisions that stay with the owner are listed in `TODO_HUMAN.md` and are not guessed here.

## 9. After the changes (2026-11-06)

### Issue status

| # | Status | Where |
|---|---|---|
| 1 PDF hash ligatures | **Fixed** + regression test with a hash containing `ff` | `app/services/exports.py`, `tests/test_exports.py` |
| 2 Re-evaluation of section/step drafts | **Fixed**; reproduced first (`pass_automated` became `fail` on re-run) | `app/routers/versions.py`, `tests/test_api.py` |
| 3 Signal-word downgrade | **Fixed** (`warning_downgraded`) | evaluator v1.4 |
| 4 Same-unit value change | **Fixed** (`value_changed`); unit tests only (no test-set SOP has such a pair) | evaluator v1.4, `tests/test_evaluator_v14.py` |
| 5 Reasons per change | **Fixed** (prompt v5 `reason`, CHANGE LOG, UI panel, `unexplained_change`); **not run on live Gemini** | `src/sop_generator.py`, `frontend/src/components/ChangeLog.jsx` |
| 6 Output retry | **Fixed** (`LLM_OUTPUT_RETRIES`) | `src/llm_client.py` |
| 7 Warning precision, consistency | **Fixed** (metrics; documented as lexical) | evaluator v1.4 |
| 8 Baselines | **Done** (EXP-004) | `evaluation/baselines.py`, `results/EXP-004_baselines.md` |
| 9 Login throttling | **Fixed** (sign-in and approval signature) | `app/limits.py` |
| 10 Password change / reset, role change | **Fixed**; sessions end on password change | `app/auth.py`, `app/routers/auth.py` |
| 11 Encrypted PDFs | **Fixed** | `app/routers/documents.py` |
| 12 Dashboard, users, audit UI | **Done** | `frontend/src/pages/` |
| 13 Register scope label | **Fixed** | `DocumentPage.jsx` |
| 14 Checks page | **Updated** | `ChecksPage.jsx` |
| 15–18 | Documented as accepted / by design | `docs/SECURITY.md` |
| 19 Docker / Postgres / OCR | **Open**: tools not available on this machine | TODO_HUMAN |
| 20 PyMuPDF licence | **Open**: owner decision | TODO_HUMAN |
| 21 Live Gemini | **Verified once** (update 2026-11-06): connectivity check and one real prompt-v5 draft (EXP-005) | `results/EXP-005_live_generation.md` |
| 22 EXP-002 labels, EXP-003 | **Open**: needs annotators | TODO_HUMAN |
| 23 Missing tests | **Done** for every change above | `tests/`, `frontend/src/test/` |

Also added: nginx security headers (CSP and others), `GET /api/overview`, `docs/ARCHITECTURE.md`,
`docs/AI_PIPELINE.md`, `docs/SECURITY.md`, evaluation framework v1.4 with a metric reference (§2.10),
logbook entry 12, corrected capstone report (it still described prompt v2, evaluator v1.2 and "no user accounts").

### Gates after the changes

| Gate | Result |
|---|---|
| Backend tests | **183 passed**, 0 failed (was 153 / 1); coverage 88 % |
| ruff · mypy | passed · passed (35 files) |
| pip-audit · npm audit | no known vulnerabilities · 0 vulnerabilities |
| Frontend lint · tests · build | passed · **11 passed** (was 5) · passed |
| EXP-001d (70 cases) | v1.4 status accuracy 0.943 (v1.3: 0.886); no result changed on the 64 earlier cases |
| EXP-004 | binary flag accuracy: SAFE-SOP v1.4 0.943, text similarity 0.729, exact warning match 0.329, always-pass 0.186 |
| Live server smoke test | 19/19 checks against `uvicorn api:app` with throwaway data (no Gemini key: generation correctly ends in 502 with no version) |
| Secret scan | no secrets in tracked or new files; no passwords or tokens in the server log |
| Browser end-to-end (2026-11-07) | 125/125 checks, 15 workflows, headless Chrome at desktop width, live Gemini (3 drafts), throwaway data; see below |

### Acceptance criteria (§12 of the brief)

| # | Criterion | Status |
|---|---|---|
| 1 | Backend starts | **Met** (live smoke test) |
| 2 | Frontend builds and runs | **Met at the HTTP level**: built, served with `vite preview`, all SPA routes return the app shell, and the bundle contains the new pages. Not clicked through in a real browser in this session (no browser automation); please do one manual run. **Update 2026-11-07:** clicked through in headless Chrome at desktop width (all 15 workflows, 125/125 checks; see "Browser end-to-end test" below). Mobile, other browsers and the Docker/nginx build not tested |
| 3 | Gemini works with local configuration | **Met** (update 2026-11-06, after the owner added `.env`): `check_gemini.py` succeeded and one real draft was generated (EXP-005) |
| 4 | Upload an SOP | **Met** (tests + live) |
| 5 | Submit a process change | **Met** (tests + live) |
| 6 | Generates a revised SOP | **Met**: with the model stubbed in tests, and once live with `gemini-3.5-flash-lite` and prompt v5 (EXP-005: one run, one change, reason given, evaluator `pass_automated`; not an accuracy result) |
| 7 | Evaluates the revision | **Met** (tests) |
| 8 | Safety-critical information checked | **Met** within the documented limits of a lexical evaluator; not validated on real model errors |
| 9 | Reviewer approves / rejects | **Met** (tests) |
| 10 | Version and audit history | **Met** (tests + live; UI pages added) |
| 11 | Approved documents exported | **Met** (tests; PDF hash defect fixed) |
| 12 | Automated tests pass | **Met** (183 + 11) |
| 13 | Security and configuration checks | **Met**; open items in `docs/SECURITY.md` §3 |
| 14 | Documentation | **Met**; human-annotation results still pending |

### Browser end-to-end test (2026-11-07)

- **Setup:** Playwright driving installed Chrome, headless, 1360 × 900, against the real API and the Vite dev server.
  Fresh throwaway database, throwaway accounts, a synthetic PDF (SOP-CENT from the test set). No real SOP was used. The
  test tooling lives outside the repository.
- **Result:** 125/125 checks across 15 workflows: sign-in/out, dashboard, users and roles, upload, extracted content,
  change request, live generation, changes and reasons, evaluation, reject/approve, history and comparison, export with
  SHA-256, audit chain, password change, and refused access. No console errors and no 5xx. All 26 4xx responses were
  refusals the tests set out to trigger.
- **Gemini:** three drafts (`gemini-3.5-flash-lite`, prompt v5). Every proposed change had a reason. All three were
  `pass_automated` with no warning or critical findings. **Three easy synthetic cases do not establish real-world
  accuracy**, and approval by a qualified reviewer is still required.
- **Defect found and fixed:** long reasons in "What changed and why" were cut off at the panel edge (cells did not wrap).
  The test reproduced it, then it was fixed (`frontend/src/index.css`, `ChangeLog.jsx`, `AuditPage.jsx`) and retested,
  with a regression test in `frontend/src/test/pages.test.jsx`. A side effect of the first fix, short audit cells
  breaking mid-word, was also fixed and retested.
- **Gates after the fix:** backend 183 passed, ruff clean; frontend lint, 11 tests and build passed.
- **Not covered:** mobile layouts, other browsers, screen readers, actual PDF rendering in the preview frame (only its
  presence was checked), and the Docker/nginx build's security headers (CSP and others).
- This does not make the system production-ready. The open items in `TODO_HUMAN.md` and `docs/SECURITY.md` §3 still apply.
