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

## Phase 3

Decisions you asked to keep for yourself:

- **PyMuPDF licence (AGPL-3.0).** PyMuPDF is used for PDF text extraction, page counts, OCR and
  PDF rendering. Under the AGPL, offering the app as a network service obliges you to publish
  the whole application's source under the AGPL, unless you buy Artifex's commercial licence.
  Options: (a) keep the project open source under the AGPL; (b) buy the commercial licence;
  (c) switch to pypdf (BSD) or pdfplumber (MIT) for text and page counts. Then OCR needs
  ocrmypdf or pytesseract, and draft PDFs need another renderer (e.g. reportlab). This touches
  `app/services/pdf.py`, `app/services/exports.py` and `app/routers/documents.py`.
- **Which fallback LLM provider to pay for.** `LLM_FALLBACK_PROVIDER` currently supports
  `ollama` (a local model, no API cost, needs a machine with a GPU or a lot of RAM). A second
  paid API (e.g. Anthropic or OpenAI) needs an adapter class in `src/llm_client.py` (about 40
  lines) and its own key and budget. Also decide whether the fallback may see the same SOP data
  (data-processing terms).
- **Hosting.** `docker-compose.yml` runs Postgres, the API and nginx on one host. Choose where it
  runs (on-premises, a VM, or a managed service such as Azure Container Apps or AWS ECS with RDS),
  plus TLS, backups of the Postgres volume and the PDF volume, and who can reach it. The API runs
  as one process (jobs and the per-minute limit live in memory): scale it up, not out, until
  those move to Redis/Postgres.
- **Regulatory-text retrieval (RAG).** Not built. If you want the model or the checklists to
  cite regulations, use only public texts (e.g. OSHA 29 CFR, US federal, public domain).
  ISO 45001 and other ISO/IEC standards are copyrighted: do not ingest them without a licence.

Could not be verified on this machine (please run once):

- **Docker:** the Docker engine was not running, so no image was built. `docker compose config`
  validates the file. Run `docker compose up --build` and sign in at http://localhost:8080.
- **Postgres:** the app and migrations are tested on SQLite only. The Postgres DDL was generated
  offline (`DATABASE_URL=postgresql+psycopg://... alembic upgrade head --sql`) and reviewed.
  The first real run against Postgres (e.g. via compose) is the real test; consider running the
  test suite against it in CI.
- **OCR:** Tesseract is not installed here; OCR is tested with a mock. The Docker image installs it.
- **Translations:** machine translations are checked only by back-translation. Before workers
  use a translated SOP, a native speaker must review it, and someone must decide whether
  translated SOPs need their own approval.
- **Checklists:** the lockout/tagout and 1910.119(f) packs paraphrase public OSHA text. A
  qualified safety professional should review the element lists and patterns before relying on them.
