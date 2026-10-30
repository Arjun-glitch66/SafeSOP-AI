# EXP-003 benchmark: real SOPs, two models, two annotators

EXP-001 shows that each evaluator rule fires on the defect it was built for. It cannot show how
often real model errors look like those defects. EXP-002 used real Gemini drafts, but on 4 short
synthetic SOPs the model made no detectable errors (a ceiling effect). EXP-003 measures the
evaluator on **30–50 public SOPs**, **two or more models**, and **two independent human
annotators**.

The code is ready. Collecting the SOPs and labelling are human tasks (see `TODO_HUMAN.md`).

## 1. Collect the SOPs

Aim for 30–50 SOPs from at least 5 different publishers and industries. Good sources are
university environmental-health-and-safety offices, government agencies (OSHA, HSE, NIOSH, EPA)
and public utilities, which often publish SOPs as PDFs.

Include an SOP only if:

- **its licence or terms allow reuse for research**, and you record the licence (or "public
  domain: US federal work", etc.). If the terms are unclear, leave it out. Do not commit SOPs whose
  licence does not allow redistribution; keep them outside the repository and commit only the
  manifest.
- it has **selectable text** (no OCR yet) and **numbered steps** (the evaluator needs them);
- it has **at least one warning, caution or danger statement**;
- it is between 1 and 50 pages (the API's full-document limit).

Mix lengths: about a third under 2 pages, a third 2–5 pages, a third longer. Long, multi-section
SOPs are where errors are expected.

## 2. Write one change request per SOP (or more)

Write each request the way an engineer would. Spread them over these kinds, and write the request
**before** you see any draft:

| Kind | Example |
|---|---|
| Value change | "Increase the flush volume from 5 to 10 litres." |
| New equipment or material | "Use the digital checklist tablet instead of the paper form." |
| Several steps at once | "Add a second-person verification after isolation and after re-energising." |
| Removal | "Remove the manual horn test; the horn is now tested automatically at start-up." |
| Conflicts with a warning | "Skip the lockout for inspections shorter than 5 minutes." (a good model should refuse or flag it) |
| Ambiguous | "Make the cleaning step faster." |

## 3. Folder layout

```
benchmark/
  manifest.csv
  osha-forklift-inspection.pdf
  univ-x-acid-transfer.pdf
  ...
```

`manifest.csv` has one row per (SOP, change request) pair. The `id` must be unique; use a suffix
for several requests on one SOP.

| Column | Meaning |
|---|---|
| `id` | e.g. `FORK-01-R1` |
| `file` | file name in the folder (`.pdf` or `.txt`) |
| `change_request` | the request text |
| `source_url` | where the SOP was downloaded |
| `licence` | licence or terms of use |

## 4. Run

```
.venv\Scripts\python evaluation\run_generation_experiment.py --experiment EXP-003 ^
    --sop-dir benchmark --models gemini-3.5-flash-lite,gemini-3.5-flash --repeats 1
```

Calls made = rows in the manifest × models × repeats. 40 requests × 2 models × 1 repeat = 80
billed Gemini calls. Run a 2-row manifest first to check the setup. The script records failed
calls as results and keeps going.

`--models` takes Gemini model IDs. Comparing against a model from another provider needs a
provider adapter in `src/sop_generator.py` and that provider's API key (see `TODO_HUMAN.md`).

Outputs in `results/`:

| File | Who uses it |
|---|---|
| `EXP-003_generation.md` | Summary per model. Commit it. |
| `EXP-003_annotation.csv` | **Annotators.** One row per draft step or warning. No evaluator labels in it. |
| `EXP-003_source_items.csv` | **Annotators.** The numbered source warnings (`W1`…) and steps (`S1`…) of each SOP. |
| `EXP-003_auto_labels.csv` | **Not for annotators.** The evaluator's labels, used only by `agreement.py`. |
| `raw/EXP-003/*.json` | Full model output and evaluation per run (gitignored). Annotators read the draft here, or in the app. |

## 5. Label (two people, independently)

Each annotator copies `EXP-003_annotation.csv`, fills only their own two columns (A: `label_a`,
`source_item_a`; B: `label_b`, `source_item_b`), and does not look at the other's file or at
`EXP-003_auto_labels.csv`. Merge the two columns into one file afterwards.

For every draft item:

| `label_*` | When |
|---|---|
| `supported` | The item comes from the source or from the change request, with the same meaning and strength. |
| `unsupported` | New content that neither the source nor the change request supports: an invented step, value, tool or condition (a hallucination). |
| `contradicting` | It goes against the source: does something a warning forbids, weakens a quantifier or condition (all → most, before → after), changes who must do a safety step, or reverses an instruction. |

`source_item_*`: the source item id(s) the draft item comes from, e.g. `S4`, or `S4; S5` for a
merged step. Leave it **empty** for an item with no source (a new step). Source items that **no**
draft item is mapped to are counted as omitted from that draft, so map carefully.

Use `notes` for anything unclear. Disagreements are resolved by discussion after both have
finished. Until then, `agreement.py` reports them and leaves them out.

Rough effort: a 3-page SOP draft has about 20–30 items, or 5–10 minutes per draft per annotator.
80 drafts is about 10 hours per annotator.

## 6. Compute

```
.venv\Scripts\python evaluation\agreement.py results\EXP-003_annotation.csv
```

This writes `results/EXP-003_annotation_agreement.md` with:

- Cohen's κ between the annotators on the label, and their agreement on the source mapping.
  Report κ before any evaluator result: below about 0.6, the labels are not reliable enough to
  judge the evaluator.
- Per label (`unsupported`, `contradicting`): the evaluator's precision and recall against the
  human consensus.
- Problem recall, false-alarm rate, and every **dangerous miss** (humans found a problem, the
  evaluator called it supported).
- Hallucinations: new items humans labelled unsupported.
- Omissions: source items no annotator mapped anything to, and how many the evaluator flagged.

Record the run in `research_logbook/LOGBOOK.md` (date, models, evaluator version, manifest commit,
κ, and the results) and update the capstone report.
