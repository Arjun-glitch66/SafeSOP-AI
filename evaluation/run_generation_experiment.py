"""
Generate real drafts with one or more Gemini models and evaluate them (EXP-002, EXP-003).

Needs GEMINI_API_KEY in .env (and GEMINI_MODEL unless --models is given). Run from the project root:
    .venv\\Scripts\\python evaluation\\run_generation_experiment.py --repeats 3
    .venv\\Scripts\\python evaluation\\run_generation_experiment.py --experiment EXP-003 \\
        --sop-dir benchmark --models gemini-3.5-flash-lite,gemini-3.5-flash --repeats 1

Without --sop-dir the 4 synthetic test-set SOPs are used. With --sop-dir, the folder needs a
manifest.csv (columns: id, file, change_request, source_url, licence) and the SOP files it names
(.pdf or .txt). See docs/BENCHMARK.md.

Writes:
    results/raw/<EXP>/<id>-<model>-run<N>.json   full model output + evaluation (gitignored)
    results/<EXP>_generation.md                  summary table per model (commit this)
    results/<EXP>_annotation.csv                 one row per DRAFT step/warning, for blind human labelling
    results/<EXP>_source_items.csv               numbered source warnings/steps the annotators map drafts to
    results/<EXP>_auto_labels.csv                the evaluator's labels; do not show to annotators
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.validate_evaluator import TESTSET, render_sop  # noqa: E402
from src.safety_evaluator import (  # noqa: E402
    EVALUATOR_VERSION,
    PARTIAL_THRESHOLD,
    best_match,
    dice,
    evaluate_revision,
    extract_draft_section,
    extract_steps,
    extract_warnings,
    tokens,
)
from src.sop_generator import PROMPT_VERSION, generate_sop  # noqa: E402

RESULTS = ROOT / "results"
METRICS = ["warning_recall", "step_coverage", "order_integrity", "unsupported_instruction_rate"]
DRAFT_LABELS = ("supported", "unsupported", "contradicting")
CONTRADICTION_TYPES = {"contradicts_warning", "conflicting_instruction", "quantifier_weakened", "actor_changed"}
OMISSION_TYPES = {"missing_warning", "omitted_step"}


def load_sops(sop_dir=None):
    """[{id, original, change_request, source}] from the synthetic test set or a benchmark folder."""
    if not sop_dir:
        testset = json.loads(TESTSET.read_text(encoding="utf-8"))
        return [{"id": sop["id"], "change_request": sop["change"]["request"], "source": "testset.json",
                 "original": render_sop(sop["title"], sop["purpose"], sop["warnings"], sop["steps"])}
                for sop in testset["sops"]]
    folder = Path(sop_dir)
    with (folder / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sops = []
    for row in rows:
        path = folder / row["file"]
        if path.suffix.lower() == ".pdf":
            import pymupdf
            with pymupdf.open(path) as pdf:
                original = "\n\n".join(page.get_text(sort=True).strip() for page in pdf)
        else:
            original = path.read_text(encoding="utf-8")
        sops.append({"id": row["id"], "original": original.strip(), "change_request": row["change_request"],
                     "source": row.get("source_url", "")})
    return sops


def source_items(original):
    """Numbered source warnings (W1..) and steps (S1..) that annotators map draft items to."""
    items = [{"item_id": f"W{n}", "item_type": "warning", "text": text}
             for n, text in enumerate(extract_warnings(original), start=1)]
    items += [{"item_id": f"S{n}", "item_type": "step", "text": step["text"]}
              for n, step in enumerate(extract_steps(original), start=1)]
    return items


def draft_items(generated_text):
    draft, _ = extract_draft_section(generated_text)
    items = [{"item_type": "warning", "text": text} for text in extract_warnings(draft)]
    items += [{"item_type": "step", "text": step["text"]} for step in extract_steps(draft)]
    return [{"draft_item_id": f"D{n}", **item} for n, item in enumerate(items, start=1)]


def auto_draft_label(text, findings):
    """The evaluator's view of one draft item, in the annotation vocabulary."""
    for finding in findings:
        if finding.get("draft") == text and finding["type"] in CONTRADICTION_TYPES and finding["severity"] != "info":
            return "contradicting"
    for finding in findings:
        if finding["type"] == "unsupported_instruction" and finding.get("draft") == text:
            return "unsupported"
        if finding["type"] == "unsupported_value" and any(
                re.search(rf"\b{re.escape(value.split()[0])}\b", text) for value in finding.get("values", [])):
            return "unsupported"
    return "supported"


def auto_source_item(text, sources):
    index, score = best_match(tokens(text), [tokens(item["text"]) for item in sources], dice)
    return sources[index]["item_id"] if index is not None and score >= PARTIAL_THRESHOLD else ""


def rows_for_run(key, generated_text, sources, findings):
    """Annotation rows (blind) and auto-label rows for one generated draft."""
    omitted = {f.get("source") for f in findings if f["type"] in OMISSION_TYPES and f["severity"] != "info"}
    annotation, auto = [], []
    for item in draft_items(generated_text):
        annotation.append({**key, "draft_item_id": item["draft_item_id"], "item_type": item["item_type"],
                           "draft_text": item["text"], "label_a": "", "source_item_a": "",
                           "label_b": "", "source_item_b": "", "notes": ""})
        auto.append({**key, "row_kind": "draft", "item_id": item["draft_item_id"],
                     "auto_label": auto_draft_label(item["text"], findings),
                     "auto_source_item": auto_source_item(item["text"], sources)})
    for item in sources:
        auto.append({**key, "row_kind": "source", "item_id": item["item_id"],
                     "auto_label": "omitted" if item["text"] in omitted else "kept", "auto_source_item": ""})
    return annotation, auto


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="EXP-002")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--sop-dir", help="benchmark folder with manifest.csv (default: synthetic test set)")
    parser.add_argument("--models", help="comma-separated model IDs (default: GEMINI_MODEL)")
    parser.add_argument("--pause", type=float, default=5.0, help="seconds between calls (rate limits)")
    args = parser.parse_args(argv)

    models = [m.strip() for m in (args.models or os.getenv("GEMINI_MODEL") or "").split(",") if m.strip()]
    if not os.getenv("GEMINI_API_KEY") or not models:
        sys.exit(f"Set GEMINI_API_KEY in {ROOT / '.env'}, and GEMINI_MODEL or --models. See README.md > Setup.")

    sops = load_sops(args.sop_dir)
    raw_dir = RESULTS / "raw" / args.experiment
    raw_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    runs, annotation_rows, auto_rows, source_rows = [], [], [], []

    for sop in sops:
        sources = source_items(sop["original"])
        source_rows += [{"experiment": args.experiment, "sop": sop["id"], **item} for item in sources]
        for model in models:
            for repeat in range(1, args.repeats + 1):
                print(f"{sop['id']} · {model} · run {repeat}/{args.repeats} ...", flush=True)
                base = {"sop": sop["id"], "model": model, "repeat": repeat}
                try:
                    result = generate_sop(original_text=sop["original"], change_request=sop["change_request"],
                                          output_scope="full", model=model)
                except Exception as exc:  # keep going; a failed call is itself a result
                    runs.append({**base, "error": f"{type(exc).__name__}: {exc}"})
                    print(f"  failed: {exc}")
                    time.sleep(args.pause)
                    continue

                evaluation = evaluate_revision(sop["original"], result["text"], sop["change_request"])
                record = {**base, "change_request": sop["change_request"], "source": sop["source"],
                          "original": sop["original"], "generation": result, "evaluation": evaluation}
                (raw_dir / f"{safe_name(sop['id'])}-{safe_name(model)}-run{repeat}.json").write_text(
                    json.dumps(record, indent=2), encoding="utf-8")
                runs.append({**base, "status": evaluation["status"],
                             **{k: evaluation["metrics"][k] for k in METRICS},
                             "failing": sum(f["severity"] in {"critical", "high"} for f in evaluation["findings"]),
                             "review": sum(f["severity"] == "review" for f in evaluation["findings"]),
                             "finding_types": sorted({f["type"] for f in evaluation["findings"] if f["severity"] != "info"})})
                annotation, auto = rows_for_run({"experiment": args.experiment, **base}, result["text"], sources,
                                                evaluation["findings"])
                annotation_rows += annotation
                auto_rows += auto
                time.sleep(args.pause)

    key_fields = ["experiment", "sop", "model", "repeat"]
    write_csv(RESULTS / f"{args.experiment}_annotation.csv", annotation_rows,
              key_fields + ["draft_item_id", "item_type", "draft_text", "label_a", "source_item_a",
                            "label_b", "source_item_b", "notes"])
    write_csv(RESULTS / f"{args.experiment}_source_items.csv", source_rows,
              ["experiment", "sop", "item_id", "item_type", "text"])
    write_csv(RESULTS / f"{args.experiment}_auto_labels.csv", auto_rows,
              key_fields + ["row_kind", "item_id", "auto_label", "auto_source_item"])

    ok = [r for r in runs if "error" not in r]
    lines = [
        f"# {args.experiment} — generation and automated evaluation",
        "",
        f"- Started (UTC): {started}",
        f"- Models: {', '.join(f'`{m}`' for m in models)} · prompt `{PROMPT_VERSION}` · evaluator `{EVALUATOR_VERSION}`",
        f"- SOP/change pairs: {len(sops)} ({'synthetic test set' if not args.sop_dir else args.sop_dir}) · "
        f"repeats: {args.repeats} · successful calls: {len(ok)}/{len(runs)}",
        "- Each draft should apply exactly one legitimate change; any other finding is a candidate generation error.",
        "",
        "| SOP | Model | Run | Status | Warning recall | Step coverage | Order integrity | Unsupported rate | Critical/high | Review | Finding types |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        if "error" in r:
            lines.append(f"| {r['sop']} | {r['model']} | {r['repeat']} | error | | | | | | | {r['error'][:80]} |")
        else:
            lines.append(f"| {r['sop']} | {r['model']} | {r['repeat']} | {r['status']} | "
                         + " | ".join(str(r[k]) for k in METRICS)
                         + f" | {r['failing']} | {r['review']} | {', '.join(r['finding_types']) or '—'} |")
    for model in models:
        model_runs = [r for r in ok if r["model"] == model]
        if not model_runs:
            continue
        lines += ["", f"## Mean over successful runs: `{model}` ({len(model_runs)} runs)", "",
                  "| Metric | Mean | Min |", "|---|---|---|"]
        for k in METRICS:
            values = [r[k] for r in model_runs if r[k] is not None]
            if values:
                lines.append(f"| {k} | {round(statistics.mean(values), 3)} | {min(values)} |")
        for status in ("fail", "needs_review", "pass_automated"):
            share = round(sum(r["status"] == status for r in model_runs) / len(model_runs), 3)
            lines.append(f"| share of runs with status {status} | {share} | |")
    lines += ["", "Automated findings are candidates. Two annotators label "
              f"`results/{args.experiment}_annotation.csv` independently (docs/BENCHMARK.md), then run "
              f"`evaluation/agreement.py results/{args.experiment}_annotation.csv`.", ""]
    (RESULTS / f"{args.experiment}_generation.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Done: {len(ok)}/{len(runs)} successful. Summary: results/{args.experiment}_generation.md")


if __name__ == "__main__":
    main()
