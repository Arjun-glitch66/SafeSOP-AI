"""
EXP-002: generate real Gemini drafts for every test-set SOP and evaluate them.

Needs GEMINI_API_KEY and GEMINI_MODEL in .env. Run from the project root:
    .venv\\Scripts\\python evaluation\\run_generation_experiment.py --repeats 3

Writes:
    results/raw/<EXP>/<SOP>-run<N>.json   full model output + evaluation (gitignored)
    results/<EXP>_generation.md           summary table (commit this)
    results/<EXP>_annotation.csv          one row per source warning/step for human labelling (commit this)
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.validate_evaluator import TESTSET, render_sop  # noqa: E402
from src.safety_evaluator import EVALUATOR_VERSION, evaluate_revision  # noqa: E402
from src.sop_generator import PROMPT_VERSION, generate_sop  # noqa: E402

RESULTS = ROOT / "results"
METRICS = ["warning_recall", "step_coverage", "order_integrity", "unsupported_instruction_rate"]


def auto_label(text, findings, preserved_label):
    for finding in findings:
        if finding.get("source") == text and finding["type"] in {"missing_warning", "omitted_step"}:
            return "missing"
        if finding.get("source") == text and finding["type"] in {"altered_warning", "altered_step"}:
            return "altered"
    return preserved_label


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="EXP-002")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--pause", type=float, default=5.0, help="seconds between calls (rate limits)")
    args = parser.parse_args()

    missing = [name for name in ("GEMINI_API_KEY", "GEMINI_MODEL") if not os.getenv(name)]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} in {ROOT / '.env'}. See README.md > Setup.")

    testset = json.loads(TESTSET.read_text(encoding="utf-8"))
    raw_dir = RESULTS / "raw" / args.experiment
    raw_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    runs, annotation_rows = [], []

    for sop in testset["sops"]:
        original = render_sop(sop["title"], sop["purpose"], sop["warnings"], sop["steps"])
        request = sop["change"]["request"]
        for repeat in range(1, args.repeats + 1):
            print(f"{sop['id']} run {repeat}/{args.repeats} ...", flush=True)
            try:
                result = generate_sop(original_text=original, change_request=request, output_scope="full")
            except Exception as exc:  # keep going; a failed call is itself a result
                runs.append({"sop": sop["id"], "repeat": repeat, "error": f"{type(exc).__name__}: {exc}"})
                print(f"  failed: {exc}")
                time.sleep(args.pause)
                continue

            evaluation = evaluate_revision(original, result["text"], request)
            record = {"sop": sop["id"], "repeat": repeat, "change_request": request, "original": original,
                      "generation": result, "evaluation": evaluation}
            (raw_dir / f"{sop['id']}-run{repeat}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            runs.append({"sop": sop["id"], "repeat": repeat, "status": evaluation["status"],
                         **{k: evaluation["metrics"][k] for k in METRICS},
                         "critical": sum(f["severity"] == "critical" for f in evaluation["findings"]),
                         "review": sum(f["severity"] == "review" for f in evaluation["findings"]),
                         "finding_types": sorted({f["type"] for f in evaluation["findings"] if f["severity"] != "info"})})

            for kind, items, preserved in (("warning", sop["warnings"], "preserved"), ("step", sop["steps"], "present")):
                for item in items:
                    annotation_rows.append({
                        "experiment": args.experiment, "sop": sop["id"], "repeat": repeat, "item_type": kind,
                        "source_text": item, "auto_label": auto_label(item, evaluation["findings"], preserved),
                        "human_label_a": "", "human_label_b": "", "notes": "",
                    })
            time.sleep(args.pause)

    with (RESULTS / f"{args.experiment}_annotation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(annotation_rows[0]) if annotation_rows else ["experiment"])
        writer.writeheader()
        writer.writerows(annotation_rows)

    ok = [r for r in runs if "error" not in r]
    lines = [
        f"# {args.experiment} — Gemini generation on the validation SOPs",
        "",
        f"- Started (UTC): {started}",
        f"- Model: `{os.getenv('GEMINI_MODEL')}` · prompt `{PROMPT_VERSION}` · evaluator `{EVALUATOR_VERSION}`",
        f"- SOPs: {len(testset['sops'])} · repeats per SOP: {args.repeats} · successful calls: {len(ok)}/{len(runs)}",
        "- Each draft should apply exactly one legitimate change; any other finding is a candidate generation error.",
        "",
        "| SOP | Run | Status | Warning recall | Step coverage | Order integrity | Unsupported rate | Critical | Review | Finding types |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        if "error" in r:
            lines.append(f"| {r['sop']} | {r['repeat']} | error | | | | | | | {r['error'][:80]} |")
        else:
            lines.append(f"| {r['sop']} | {r['repeat']} | {r['status']} | " + " | ".join(str(r[k]) for k in METRICS)
                         + f" | {r['critical']} | {r['review']} | {', '.join(r['finding_types']) or '—'} |")
    if ok:
        lines += ["", "## Mean over successful runs", "", "| Metric | Mean | Min |", "|---|---|---|"]
        for k in METRICS:
            values = [r[k] for r in ok if r[k] is not None]
            if values:
                lines.append(f"| {k} | {round(statistics.mean(values), 3)} | {min(values)} |")
        for status in ("fail", "needs_review", "pass_automated"):
            lines.append(f"| share of runs with status {status} | {round(sum(r['status'] == status for r in ok) / len(ok), 3)} | |")
    lines += ["", "Automated findings are candidates. Two annotators fill `human_label_a` and `human_label_b` "
              "independently (research_logbook/EVALUATION_FRAMEWORK.md, section 6), then run "
              f"`evaluation/agreement.py results/{args.experiment}_annotation.csv`.", ""]
    (RESULTS / f"{args.experiment}_generation.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Done: {len(ok)}/{len(runs)} successful. Summary: results/{args.experiment}_generation.md")


if __name__ == "__main__":
    main()
