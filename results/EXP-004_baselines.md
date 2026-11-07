# EXP-004 — SAFE-SOP evaluator against simple baselines

- Date (UTC): 2026-11-06 17:35 · git `78033ce+uncommitted-src-changes`
- Cases: 70 from `evaluation/testset.json` (57 with a defect, 13 clean), built exactly as in EXP-001
- B2 threshold 0.9, fixed before the first run (not tuned)

| Method | Status accuracy (3-way) | Flag accuracy (binary) | Defects flagged | Clean false alarms |
|---|---|---|---|---|
| B0 always-pass | 0.186 | 0.186 | 0.0 | 0.0 |
| B1 exact-warning | 0.3 | 0.329 | 0.228 | 0.231 |
| B2 text-similarity (<0.9) | 0.629 | 0.729 | 0.825 | 0.692 |
| SAFE-SOP safe-sop-eval-1.4 | 0.943 | 0.943 | 0.947 | 0.077 |

Flag accuracy by case group:

| Method | hard-dev | hard-dev-v1.4 | hard-heldout | standard |
|---|---|---|---|---|
| B0 always-pass | 0.125 | 0.333 | 0.25 | 0.125 |
| B1 exact-warning | 0.125 | 0.667 | 0.417 | 0.25 |
| B2 text-similarity (<0.9) | 0.75 | 0.667 | 0.542 | 0.875 |
| SAFE-SOP safe-sop-eval-1.4 | 0.875 | 1.0 | 0.875 | 1.0 |

Baselines cannot answer "needs review", so their 3-way status accuracy is lower by construction; compare the binary flag accuracy. The cases are synthetic, written by the author of the rules, and partly used to design them (groups `hard-dev*`); `hard-heldout` was written before the rules it tests but by the same author. This shows what each method catches on known defect types, not real-world accuracy.
