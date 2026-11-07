# SafeSOP AI — Security considerations and deployment checklist

Audience: whoever deploys or assesses the system. Status as of 2026-11-06; review findings in
[PROJECT_COMPLETION_AUDIT.md](../PROJECT_COMPLETION_AUDIT.md).

## 1. Threat model (short)

Assets: the integrity of approved procedures and their approval records; uploaded SOPs (may be
confidential); user credentials; the Gemini API key and budget. Assumed deployment: one organisation, on a
trusted network or behind TLS, every user known to an admin. Out of scope: a malicious database or host
administrator (they can rewrite anything, including a consistent audit chain).

## 2. Controls in place

| Area | Control | Where |
|---|---|---|
| Secrets | Keys and passwords only in environment / `.env` (gitignored; `.env.example` has empty values). The frontend knows only the API base URL. Keys are never logged or returned. | `app/config.py`, `.gitignore` |
| Passwords | bcrypt, 12 rounds, minimum 10 characters; constant-work check for unknown usernames | `app/auth.py` |
| Sessions | HS256 JWT, 8 h expiry, user re-read on every request (a deleted user or a changed role takes effect at once). Tokens carry a fingerprint of the password hash, so **a password change or admin reset ends all older sessions**. Startup warns when `JWT_SECRET` is missing or shorter than 32 bytes. | `app/auth.py` |
| Brute force | Sign-in and the approval signature are throttled: 5 failures per username and 20 per client address per 15 minutes → 429 with `Retry-After` | `app/limits.py` |
| Authorisation | Sign-in required on all data routes; roles on writes; admin-only user management and audit listing; separation of duties (no approving your own draft); approval lock; server-side justification rule | `app/main.py`, routers |
| Uploads | 20 MB streamed cap, `%PDF-` magic bytes, must open, not encrypted, ≥ 1 page; stored under a random UUID; never modified; SHA-256 recorded | `app/routers/documents.py` |
| Cost abuse | Per-user 5/min and 100/day on generation; size limits checked before the model call | `app/limits.py`, `app/services/generation.py` |
| Injection | SQL: bound parameters only. HTML in exports: escaped. Prompt injection: see [AI_PIPELINE.md §3](AI_PIPELINE.md) | |
| Audit integrity | Append-only table (UPDATE/DELETE refused by triggers on SQLite), SHA-256 hash chain, write lock on the head, `GET /api/audit/verify` and the Audit log page | `app/audit.py` |
| Exports | Fingerprints printed in a ligature-free font so a copied hash verifies | `app/services/exports.py` |
| Browser | nginx sends a strict CSP (`script-src 'self'`, no inline code), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` | `frontend/nginx.conf` |
| Dependencies | `pip-audit` and `npm audit` in CI; both clean on 2026-11-06 | `.github/workflows/ci.yml` |

## 3. Known gaps and accepted risks

| Gap | Risk | Mitigation / next step |
|---|---|---|
| Token kept in `localStorage` | Readable by injected script (XSS) | No third-party scripts, React escaping, CSP. Next step: httpOnly SameSite cookie + CSRF token |
| Throttling and per-minute limits live in process memory | Reset on restart; not shared between processes | Run one API process (already required by jobs); move to Redis/Postgres to scale out |
| Per-username throttling lets an attacker lock a known user out for 15 minutes | Nuisance denial of service | Short window; admin can reset; consider CAPTCHA or allow-listing at the proxy |
| No per-document access control | Every signed-in user can read every SOP | Single-organisation design; add document ACLs before multi-tenant use |
| No MFA / SSO | Password-only sign-in | Put the app behind the organisation's SSO proxy if available |
| Audit chain can be rewritten consistently by a DB superuser | Undetectable tampering by an insider with DB access | Periodically record the head hash (`/api/audit/verify` → `head`) outside the system |
| Failed sign-ins log the attempted username | A password typed into the username field reaches the log | Usernames are truncated to 100 characters; restrict log access |
| SOP text is sent to Google (and to Anthropic if `SEMANTIC_CHECK=llm`) | Data leaves the organisation | Check the data-processing terms for your SOPs; use the Ollama fallback for data that may not leave |
| PyMuPDF is AGPL-3.0 | Licence obligations for a network service | Owner decision (TODO_HUMAN.md) |

## 4. Deployment checklist

1. Copy `.env.example` to `.env`; set `GEMINI_API_KEY`, `GEMINI_MODEL`, a random `JWT_SECRET`
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`), `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
   and for compose `POSTGRES_PASSWORD`. Never commit `.env`.
2. Terminate TLS in front of nginx (port 8080 in compose). Do not publish the backend port: uvicorn trusts
   `X-Forwarded-For` from any address (`--forwarded-allow-ips "*"`), which is only safe because compose keeps
   the API on the internal network behind nginx.
3. Set `ALLOWED_ORIGINS` to the real site origin.
4. Run exactly one API process.
5. Back up the Postgres volume **and** the PDF volume together (versions reference files).
6. After the first start: sign in as admin, create named author and reviewer accounts on the Users page,
   and change the admin password on the Account page.
7. Verify: `GET /readyz` is 200; Audit log → "Verify chain" says intact; `python scripts/check_gemini.py`
   succeeds (one billed call).
