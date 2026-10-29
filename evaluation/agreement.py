"""
Compare automated labels with human labels in an annotation CSV (from run_generation_experiment.py).

    .venv\\Scripts\\python evaluation\\agreement.py results\\EXP-002_annotation.csv

Writes results/<csv name>_agreement.md with:
- Cohen's kappa between annotator A and annotator B (inter-annotator agreement)
- evaluator accuracy against the human consensus, per item type
- recall of human-labelled problems (missing / altered), and every dangerous miss listed
"""
import csv
import sys
from collections import Counter
from pathlib import Path

# preserved (warnings) and present (steps) mean the same thing: the item was kept.
NORMALISE = {"preserved": "kept", "present": "kept", "altered": "altered", "missing": "missing",
             "uncertain": "uncertain"}
PROBLEMS = {"altered", "missing", "uncertain"}  # uncertain counts as not preserved (framework section 6)


def label(value):
    value = (value or "").strip().lower()
    if value and value not in NORMALISE:
        raise ValueError(f"Unknown label '{value}'. Use: {', '.join(sorted(NORMALISE))}")
    return NORMALISE.get(value)


def cohens_kappa(pairs):
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    count_a, count_b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(count_a[k] * count_b[k] for k in count_a) / (n * n)
    return 1.0 if expected == 1 else round((observed - expected) / (1 - expected), 3)


def analyse(rows):
    pairs, judged, disagreements = [], [], 0
    for row in rows:
        a, b = label(row.get("human_label_a")), label(row.get("human_label_b"))
        if a and b:
            pairs.append((a, b))
        if a and b and a != b:
            disagreements += 1
            continue  # resolve by discussion first; excluded until then
        consensus = a or b
        if consensus:
            judged.append({**row, "human": consensus, "auto": label(row["auto_label"])})

    per_type = {}
    for kind in sorted({r["item_type"] for r in judged}):
        items = [r for r in judged if r["item_type"] == kind]
        per_type[kind] = {"items": len(items),
                          "accuracy": round(sum(r["auto"] == r["human"] for r in items) / len(items), 3)}

    problems = [r for r in judged if r["human"] in PROBLEMS]
    flagged = [r for r in problems if r["auto"] in PROBLEMS]
    missing = [r for r in judged if r["human"] == "missing"]
    false_alarms = [r for r in judged if r["human"] == "kept" and r["auto"] in PROBLEMS]
    kept = [r for r in judged if r["human"] == "kept"]
    return {
        "rows": len(rows),
        "double_labelled": len(pairs),
        "kappa": cohens_kappa(pairs),
        "unresolved_disagreements": disagreements,
        "judged": len(judged),
        "per_type": per_type,
        "problem_recall": round(len(flagged) / len(problems), 3) if problems else None,
        "missing_recall": round(sum(r["auto"] == "missing" for r in missing) / len(missing), 3) if missing else None,
        "false_alarm_rate": round(len(false_alarms) / len(kept), 3) if kept else None,
        "dangerous_misses": [r for r in problems if r["auto"] not in PROBLEMS],
    }


def write_report(result, csv_path):
    lines = [
        f"# Human vs automated agreement — {csv_path.name}",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Rows | {result['rows']} |",
        f"| Labelled by both annotators | {result['double_labelled']} |",
        f"| Cohen's kappa (A vs B) | {result['kappa']} |",
        f"| Unresolved A/B disagreements (excluded below) | {result['unresolved_disagreements']} |",
        f"| Items with a human consensus label | {result['judged']} |",
        f"| Recall of human-labelled problems (auto flagged missing/altered) | {result['problem_recall']} |",
        f"| Recall of human-labelled *missing* items (auto said missing) | {result['missing_recall']} |",
        f"| False alarm rate on items humans marked kept | {result['false_alarm_rate']} |",
        "",
        "| Item type | Items | Evaluator accuracy |",
        "|---|---|---|",
        *[f"| {k} | {v['items']} | {v['accuracy']} |" for k, v in result["per_type"].items()],
        "",
        "## Dangerous misses (human found a problem, evaluator said kept)",
        "",
    ]
    if result["dangerous_misses"]:
        lines += ["| SOP | Run | Type | Source text | Human |", "|---|---|---|---|---|"]
        lines += [f"| {r['sop']} | {r['repeat']} | {r['item_type']} | {r['source_text']} | {r['human']} |"
                  for r in result["dangerous_misses"]]
    else:
        lines.append("None.")
    out = csv_path.with_name(csv_path.stem + "_agreement.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python evaluation/agreement.py results/EXP-002_annotation.csv")
    csv_path = Path(sys.argv[1])
    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = analyse(rows)
    if not result["judged"]:
        sys.exit("No human labels yet. Fill human_label_a / human_label_b first.")
    print(f"kappa={result['kappa']} problem_recall={result['problem_recall']} "
          f"dangerous_misses={len(result['dangerous_misses'])} -> {write_report(result, csv_path)}")


if __name__ == "__main__":
    main()
