# SafeSOP AI — AI generation pipeline and prompt engineering

Audience: anyone who needs to understand, review or change how drafts are generated.
Code: `app/services/generation.py`, `src/sop_generator.py`, `src/llm_client.py`, `src/translator.py`.

## 1. Pipeline

| Stage | What happens | Failure behaviour |
|---|---|---|
| 1. Fail fast (`prepare_generation`) | Rate limit and daily quota; the document, parent version and saved request exist; scope and target are valid; the **original PDF** is read (OCR for scanned pages if Tesseract is present); page limit (50, full scope) and text limit (60,000 characters) | 4xx/413/429 **before** any billed model call; nothing is created except, once inputs are valid, the change-request record |
| 2. Prompt | Source warnings and steps are numbered (W1…, S1…) with the same extraction the evaluator uses. Rules go in the system instruction; document text, numbered items and reviewer comments go in the user message inside per-request random boundaries | — |
| 3. Model call (`llm_client.generate`) | Gemini with `response_schema = SopDraft` (pydantic), temperature 0.2 (`GEMINI_TEMPERATURE`), 120 s timeout | The SDK retries 429/5xx with backoff (4 attempts). Unusable output (truncated, blocked, empty) is asked for again `LLM_OUTPUT_RETRIES` times (default 1). Then the optional fallback provider (recorded on the version). Then 502 and **no version** |
| 4. Render | The JSON becomes text: preamble, warnings, kept steps renumbered, then CHANGE SUMMARY, CHANGE LOG, PRESERVED SAFETY REQUIREMENTS, UNRESOLVED QUESTIONS, SOURCE LIMITATIONS. Section/step scope: only the target part was sent; it is spliced back into the original text, everything else byte for byte | — |
| 5. Save | Next version number under a write lock, with model, provider, prompt version, temperature, tokens, the JSON and an audit event with the text's SHA-256 | 500, the model's answer is not kept |
| 6. Translate (optional) | Separate translate and back-translate calls; the English draft remains the controlled text | A failed translation keeps the English draft and adds a review finding |
| 7. Evaluate | SAFE-SOP v1.4 against the original (structured path by id for full/page scope; text path for section/step scope and older drafts). OCR and translation findings can only raise the status | An evaluator crash keeps the draft and reports "not evaluated" |

Every version is a **draft** pending human approval. Nothing in the pipeline can approve.

## 2. Output schema (prompt v5)

```text
SopDraft
  preamble: str
  warnings: [ {id: "RW1"…, text, source_warning_id: "W2" | null, reason} ]
  removed_warning_ids: ["W3", …]
  steps:    [ {id: "R1"…, text, source_step_ids: ["S1", …], change_type: unchanged|modified|added|removed, reason} ]
  change_summary, preserved_safety_requirements, unresolved_questions, source_limitations: str
```

How each requirement is met:

| Requirement | Mechanism | Checked by |
|---|---|---|
| Preserve warnings | Rule 3; every W id must be carried or listed in `removed_warning_ids` | `missing_warning`, `warning_removed` (critical even when declared), `altered_warning`, `warning_downgraded` |
| Preserve critical instructions | Rules 3–4 | `contradicts_warning`, `missing_required_element`, `control_downgraded` |
| Preserve ordering | Rule 4; steps listed in revised order with their S ids | `step_order_violation` |
| No invented instructions | Rules 2 and 5; new steps must be `added` with no source id | `unsupported_instruction`, `unsupported_value`, `value_changed` |
| Missing information and conflicts flagged, not fabricated | Rule 6; `unresolved_questions`, `source_limitations` | Shown to the reviewer; not machine-checked |
| Original vs modified content | `change_type` and source ids per step; side-by-side diff in the UI | `altered_step` (a step labelled unchanged that changed is flagged) |
| A reason for every modification | `reason` field (v5); rendered in CHANGE LOG and the "What changed and why" panel; "NO REASON GIVEN" when empty | `unexplained_change` |
| Marked as a draft | Rules 7–8; status `draft`; downloads carry an "AI-generated draft – not valid until approved" header | Approval only through the signed review endpoint |

The model's own claims (`preserved_safety_requirements`, `change_type: unchanged`, its reasons) are
**never trusted** by the evaluator; they are compared with the source or shown as claims.

## 3. Prompt-injection hardening (since v4)

- Rules live only in the system instruction; the uploaded text never sits next to them.
- Untrusted text (SOP, numbered items, reviewer comments) is wrapped in `<<<NAME token>>> … <<<END NAME token>>>`
  with a fresh 128-bit token per request; the system instruction says text claiming to end a block with any
  other token is data. Tested with a PDF containing "IGNORE ALL PREVIOUS INSTRUCTIONS" and a forged end marker.
- The response is constrained to the schema, so injected text cannot add fields such as "approved".
- Residual risk: a model can still be steered within the schema (e.g. drop a warning). That is what the
  evaluator and the signed human review are for. Injection resistance has not been measured on a real model.

## 4. Prompt versions

| Version | Change |
|---|---|
| v1 | Plain-text sections |
| v2 | JSON enforced by `response_schema` |
| v3 | Numbered source items; steps and warnings cite ids |
| v4 | Rules in the system instruction; random boundary markers |
| v5 (2026-11-06) | `reason` on every step and warning; CHANGE LOG; keep the source's signal word |

Every version stores `prompt_version`, so results are always attributable. Automated tests use a stub.
**Live check (EXP-005, 2026-11-06):** prompt v5 was run once against the real model `gemini-3.5-flash-lite`
through the running API. The response matched the schema, every item cited the right source id, and the one
changed step carried a stated reason (unchanged items had an empty one, as instructed). This is one successful run
on an easy synthetic case, not evidence of how reliably the model follows the prompt
(`results/EXP-005_live_generation.md`).

## 5. Configuration

`GEMINI_API_KEY`, `GEMINI_MODEL` (required), `GEMINI_TEMPERATURE` (0.2), `LLM_PROVIDER` (gemini),
`LLM_FALLBACK_PROVIDER` (none; `ollama` supported), `OLLAMA_URL`, `OLLAMA_MODEL`, `LLM_OUTPUT_RETRIES` (1).
Keys are read from the environment only and never logged or returned to the browser.
