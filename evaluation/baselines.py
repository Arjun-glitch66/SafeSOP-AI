"""
EXP-004: the SAFE-SOP evaluator against simple baselines on the same labelled cases as EXP-001.

Run from the project root (no API key needed):
    .venv\\Scripts\\python evaluation\\baselines.py

Every method sees the same original text, change request and draft for each case built by
validate_evaluator.build_cases() from evaluation/testset.json. Baselines:

  B0 always-pass        Reports every draft as "no problem". The floor: what a reviewer gets with no tool.
  B1 exact-warning      The project's first, label-free idea (normalize_text in safety_evaluator.py):
                        fail if any source warning line is not found verbatim (after lower-casing and
                        removing punctuation) among the draft lines. Nothing else is checked.
  B2 text-similarity    difflib ratio between the original lines and the draft lines; fail below 0.90.
                        A generic "did the text change a lot?" detector.

The B2 threshold (0.90) was fixed when this script was written, before it was first run, and is not
tuned on these cases. Baselines only decide flag / no flag (they have no "needs review"), so two
accuracies are reported: the three-way status accuracy (where they are disadvantaged by design) and the
binary flag accuracy (flag any defect case, pass every clean case), which compares like with like.

Writes results/EXP-004_baselines.json and .md. The cases are synthetic and written by the rules'
author: this compares methods on known defect types; it is not evidence of real-world accuracy.
"""
import difflib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.validate_evaluator import TESTSET, build_cases, git_commit  # noqa: E402
from src.safety_evaluator import (  # noqa: E402
    EVALUATOR_VERSION,
    evaluate_revision,
    extract_draft_section,
    extract_warnings,
    normalize_text,
    text_lines,
)

RESULTS = ROOT / "results"
SIMILARITY_THRESHOLD = 0.90  # B2; fixed before the first run


def always_pass(case):
    return "pass_automated"


def exact_warning(case):
    draft_lines = {normalize_text(line) for line in text_lines(extract_draft_section(case["draft"])[0])}
    missing = [w for w in extract_warnings(case["original"]) if normalize_text(w) not in draft_lines]
    return "fail" if missing else "pass_automated"


def text_similarity(case):
    original = [normalize_text(line) for line in text_lines(case["original"])]
    draft = [normalize_text(line) for line in text_lines(extract_draft_section(case["draft"])[0])]
    ratio = difflib.SequenceMatcher(a=original, b=draft, autojunk=False).ratio()
    return "fail" if ratio < SIMILARITY_THRESHOLD else "pass_automated"


def safe_sop(case):
    return evaluate_revision(case["original"], case["draft"], case["change_request"])["status"]


METHODS = [
    ("B0 always-pass", always_pass),
    ("B1 exact-warning", exact_warning),
    (f"B2 text-similarity (<{SIMILARITY_THRESHOLD})", text_similarity),
    (f"SAFE-SOP {EVALUATOR_VERSION}", safe_sop),
]


def ratio(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else None


def summarise(cases, statuses):
    defect = [i for i, c in enumerate(cases) if c["expected_status"] != "pass_automated"]
    clean = [i for i, c in enumerate(cases) if c["expected_status"] == "pass_automated"]
    flagged = [s != "pass_automated" for s in statuses]
    groups = {}
    for group in sorted({c["group"] for c in cases}):
        members = [i for i, c in enumerate(cases) if c["group"] == group]
        groups[group] = ratio(sum(flagged[i] == (cases[i]["expected_status"] != "pass_automated") for i in members),
                              len(members))
    return {
        "status_accuracy": ratio(sum(s == c["expected_status"] for s, c in zip(statuses, cases, strict=True)), len(cases)),
        "flag_accuracy": ratio(sum(flagged[i] for i in defect) + sum(not flagged[i] for i in clean), len(cases)),
        "defects_flagged": ratio(sum(flagged[i] for i in defect), len(defect)),
        "clean_false_alarms": ratio(sum(flagged[i] for i in clean), len(clean)),
        "flag_accuracy_by_group": groups,
    }


def main():
    cases = build_cases(json.loads(TESTSET.read_text(encoding="utf-8")))
    results = {name: summarise(cases, [method(case) for case in cases]) for name, method in METHODS}
    defect = sum(c["expected_status"] != "pass_automated" for c in cases)
    summary = {"experiment_id": "EXP-004", "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
               "git_commit": git_commit(), "cases": len(cases), "defect_cases": defect,
               "clean_cases": len(cases) - defect, "methods": results}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "EXP-004_baselines.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    groups = sorted(next(iter(results.values()))["flag_accuracy_by_group"])
    lines = [
        "# EXP-004 — SAFE-SOP evaluator against simple baselines",
        "",
        f"- Date (UTC): {summary['run_at']} · git `{summary['git_commit']}`",
        f"- Cases: {len(cases)} from `evaluation/testset.json` ({defect} with a defect, {len(cases) - defect} clean), "
        "built exactly as in EXP-001",
        f"- B2 threshold {SIMILARITY_THRESHOLD}, fixed before the first run (not tuned)",
        "",
        "| Method | Status accuracy (3-way) | Flag accuracy (binary) | Defects flagged | Clean false alarms |",
        "|---|---|---|---|---|",
        *[f"| {name} | {m['status_accuracy']} | {m['flag_accuracy']} | {m['defects_flagged']} | {m['clean_false_alarms']} |"
          for name, m in results.items()],
        "",
        "Flag accuracy by case group:",
        "",
        "| Method | " + " | ".join(groups) + " |",
        "|---|" + "---|" * len(groups),
        *[f"| {name} | " + " | ".join(str(m["flag_accuracy_by_group"][g]) for g in groups) + " |"
          for name, m in results.items()],
        "",
        "Baselines cannot answer \"needs review\", so their 3-way status accuracy is lower by construction; "
        "compare the binary flag accuracy. The cases are synthetic, written by the author of the rules, and "
        "partly used to design them (groups `hard-dev*`); `hard-heldout` was written before the rules it tests "
        "but by the same author. This shows what each method catches on known defect types, not real-world accuracy.",
    ]
    (RESULTS / "EXP-004_baselines.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[7:7 + 2 + len(results)]))
    print("written: results/EXP-004_baselines.md")


if __name__ == "__main__":
    main()
