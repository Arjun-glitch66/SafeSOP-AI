# EXP-005 — One live generation with prompt v5 and evaluator v1.4

**One successful real-model run. A functional check of the live pipeline, not an accuracy result:** one SOP,
one change request, one run, no repeats, no human labels. It says nothing statistically reliable about how
often the model makes errors or how well the evaluator catches them.

## Setup

| Item | Value |
|---|---|
| Date (UTC) | 2026-11-06 19:49 (version `created_at`) |
| Code | git `78033ce` + uncommitted completion-phase changes (prompt v5, evaluator v1.4) |
| Path exercised | The running API (`uvicorn api:app`, throwaway data folder): sign-in → PDF upload → `POST /generate` (202) → background job → Gemini → save → evaluation. Not a stub. |
| Connectivity check first | `scripts/check_gemini.py`: `SUCCESS: SafeSOP AI connected` |
| Provider / model | Google Gemini, `gemini-3.5-flash-lite`; fallback provider not configured and not used |
| Prompt | v5 (structured JSON, `reason` per step and warning) · temperature 0.2 · scope `full` |
| Source document | SOP-ACID "Concentrated Acid Drum Transfer" from `evaluation/testset.json` (synthetic, written for this project), rendered as a one-page PDF: title, purpose, 4 warnings (WARNING ×2, CAUTION, DANGER), 8 numbered steps |
| Change request | "Increase the pump flush volume from 5 litres to 10 litres of clean water." (the test set's legitimate change for this SOP) |

## Results

| Measure | Value |
|---|---|
| Job outcome | succeeded, no fallback, structured output |
| Generation time | 3.6 s from `POST /generate` to job `succeeded` (client-side, polled every 0.5 s, so ±0.5 s; includes saving and evaluation) |
| Tokens | 1,498 input · 960 output |
| Steps changed by the model | 1 of 8: step 6 `modified` (from S6); 7 `unchanged` |
| Reasons | Step 6: "Increased the pump flush volume from 5 litres to 10 litres as requested by the engineer change request." Unchanged steps and the 4 carried warnings: empty reason, as instructed. `unexplained_changes` = 0 |
| Warnings | 4 of 4 carried by id (W1–W4); none removed |
| Evaluator | `safe-sop-eval-1.4+structured`, status `pass_automated` ("no rule fired"), 0 findings |
| Evaluator metrics | warning recall 1.0 · warning precision 1.0 · step coverage 1.0 · order integrity 1.0 · unsupported instruction rate 0.0 · unsupported values 0 · changed values 0 · downgraded warnings 0 · lexical consistency 1.0 · change applied: yes |
| Independent check (script comparing draft with source text, not using the evaluator) | All 4 warnings word for word with the same signal words and order; 8 steps in the same order; the only difference in the procedure is "5" → "10" in step 6; no numbers or lines that are not in the source or the request |
| Version status | `draft`: not reviewed, not approved |

Generated DRAFT section (as stored):

```text
Concentrated Acid Drum Transfer
Purpose: Transfer concentrated sulphuric acid from a 200 litre drum into process containers.
WARNING: Wear chemical splash goggles and a face shield during transfer.
WARNING: Never add water to the concentrated acid.
CAUTION: Keep the emergency eyewash station clear and within 10 metres.
DANGER: Do not transfer acid without secondary containment in place.
1. Check the drum label against the transfer request form.
2. Position the drum on the spill containment pallet.
3. Connect the grounding clamp to the drum and the receiving container.
4. Insert the drum pump and tighten the bung adapter by hand.
5. Pump the acid slowly into the receiving container up to the fill line.
6. Flush the pump with 10 litres of clean water into the neutralisation tank.
7. Record the transferred volume in the chemical inventory log.
8. Inspect the area for drips and report any spill to the supervisor.
```

CHANGE LOG section: `- R6 modified from S6: Increased the pump flush volume from 5 litres to 10 litres as requested by the engineer change request.`

## Interpretation and limits

- **Shown:** the live integration works end to end with prompt v5; the model filled the new `reason` field for
  its one change and left it empty for unchanged items; the structured output carried every source id; the
  evaluator ran on real output.
- **Not shown:** error rates. This is the easiest kind of case (short, well-structured SOP, one requested value
  change) and the same ceiling effect as EXP-002: with no model error to catch, it cannot test the evaluator's
  recall. The model's own statement that all warnings were preserved happened to be true; the evaluator never
  relies on it.
- `pass_automated` is not a safety approval. The draft would still need a qualified human reviewer's signed
  approval before use.
- Harder inputs (longer public SOPs, several or conflicting changes, repeats, two annotators) are what EXP-003
  is for (`docs/BENCHMARK.md`).
