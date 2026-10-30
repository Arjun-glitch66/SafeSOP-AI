"""
Compare automated labels with human labels in an annotation CSV (from run_generation_experiment.py).

    .venv\\Scripts\\python evaluation\\agreement.py results\\EXP-003_annotation.csv

Two formats, picked by the CSV header:

- Draft-item format (EXP-003 on; columns label_a, source_item_a, label_b, source_item_b): one row
  per draft step or warning, labelled supported / unsupported / contradicting and mapped to the
  source item(s) it comes from. The evaluator's labels are read from <EXP>_auto_labels.csv and the
  source items from <EXP>_source_items.csv next to it.
- Source-item format (EXP-002; columns human_label_a, human_label_b): one row per source item.

Writes results/<csv name>_agreement.md with Cohen's kappa between annotator A and B, the
evaluator against the human consensus, and every dangerous miss listed.
"""
import csv
import re
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


# ---- Draft-item format (EXP-003 on) ----

DRAFT_LABELS = {"supported", "unsupported", "contradicting"}
DRAFT_PROBLEMS = {"unsupported", "contradicting"}


def draft_label(value):
    value = (value or "").strip().lower()
    if value and value not in DRAFT_LABELS:
        raise ValueError(f"Unknown label '{value}'. Use: {', '.join(sorted(DRAFT_LABELS))}")
    return value or None


def source_ids(value):
    """'S3; S4' -> {'S3', 'S4'}. Empty means a new item with no source."""
    return frozenset(part.upper() for part in re.split(r"[;,\s]+", value or "") if part)


def run_key(row):
    return row["sop"], row["model"], str(row["repeat"])


def analyse_draft_items(rows, auto_rows, source_rows):
    auto = {(*run_key(r), r["item_id"]): r for r in auto_rows}
    label_pairs, mapping_pairs, judged, disagreements = [], [], [], 0
    mapped = {}  # run -> source ids that any annotator mapped a draft item to
    for row in rows:
        a, b = draft_label(row.get("label_a")), draft_label(row.get("label_b"))
        sa, sb = source_ids(row.get("source_item_a")), source_ids(row.get("source_item_b"))
        mapped.setdefault(run_key(row), set()).update(sa | sb)
        if a and b:
            label_pairs.append((a, b))
            mapping_pairs.append((sa, sb))
            if a != b:
                disagreements += 1
                continue  # resolve by discussion first; excluded until then
        consensus = a or b
        if consensus:
            prediction = auto.get((*run_key(row), row["draft_item_id"]), {})
            judged.append({**row, "human": consensus, "auto": prediction.get("auto_label"),
                           "new_item": not (sa | sb)})

    per_label = {}
    for kind in sorted(DRAFT_PROBLEMS):
        tp = sum(r["human"] == kind and r["auto"] == kind for r in judged)
        fp = sum(r["human"] != kind and r["auto"] == kind for r in judged)
        fn = sum(r["human"] == kind and r["auto"] != kind for r in judged)
        per_label[kind] = {"human": tp + fn, "tp": tp, "fp": fp, "fn": fn,
                           "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                           "recall": round(tp / (tp + fn), 3) if tp + fn else None}

    problems = [r for r in judged if r["human"] in DRAFT_PROBLEMS]
    supported = [r for r in judged if r["human"] == "supported"]

    # Omissions: a source item that no annotator mapped any draft item to was left out of that draft.
    annotated_runs = {run_key(r) for r in rows if r.get("label_a") or r.get("label_b")}
    auto_omitted = {(*run_key(r), r["item_id"]) for r in auto_rows
                    if r["row_kind"] == "source" and r["auto_label"] == "omitted"}
    human_omitted = [{"run": run, **item} for run in sorted(annotated_runs) for item in source_rows
                     if item["sop"] == run[0] and item["item_id"].upper() not in mapped.get(run, set())]
    caught = [o for o in human_omitted if (*o["run"], o["item_id"]) in auto_omitted]

    return {
        "rows": len(rows),
        "double_labelled": len(label_pairs),
        "kappa": cohens_kappa(label_pairs),
        "mapping_agreement": round(sum(a == b for a, b in mapping_pairs) / len(mapping_pairs), 3) if mapping_pairs else None,
        "unresolved_disagreements": disagreements,
        "judged": len(judged),
        "human_label_counts": dict(Counter(r["human"] for r in judged)),
        "new_unsupported_items": sum(r["human"] == "unsupported" and r["new_item"] for r in judged),
        "per_label": per_label,
        "problem_recall": round(sum(r["auto"] in DRAFT_PROBLEMS for r in problems) / len(problems), 3) if problems else None,
        "false_alarm_rate": round(sum(r["auto"] in DRAFT_PROBLEMS for r in supported) / len(supported), 3) if supported else None,
        "dangerous_misses": [r for r in problems if r["auto"] not in DRAFT_PROBLEMS],
        "human_omissions": len(human_omitted),
        "omission_recall": round(len(caught) / len(human_omitted), 3) if human_omitted else None,
        "missed_omissions": [o for o in human_omitted if o not in caught],
    }


def write_draft_report(result, csv_path):
    counts = ", ".join(f"{k} {v}" for k, v in sorted(result["human_label_counts"].items())) or "—"
    lines = [
        f"# Human vs automated agreement (draft items) — {csv_path.name}",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Draft items | {result['rows']} |",
        f"| Labelled by both annotators | {result['double_labelled']} |",
        f"| Cohen's kappa, label (A vs B) | {result['kappa']} |",
        f"| Agreement on source-item mapping (A vs B) | {result['mapping_agreement']} |",
        f"| Unresolved A/B label disagreements (excluded below) | {result['unresolved_disagreements']} |",
        f"| Items with a human consensus label | {result['judged']} |",
        f"| Human labels | {counts} |",
        f"| New items (no source mapping) labelled unsupported, i.e. hallucinations | {result['new_unsupported_items']} |",
        f"| Recall of human-labelled problems (auto said unsupported/contradicting) | {result['problem_recall']} |",
        f"| False alarm rate on items humans marked supported | {result['false_alarm_rate']} |",
        f"| Source items no draft item maps to (human-found omissions) | {result['human_omissions']} |",
        f"| Omission recall (evaluator flagged the item missing/omitted) | {result['omission_recall']} |",
        "",
        "| Label | Human count | TP | FP | FN | Precision | Recall |",
        "|---|---|---|---|---|---|---|",
        *[f"| {k} | {v['human']} | {v['tp']} | {v['fp']} | {v['fn']} | {v['precision']} | {v['recall']} |"
          for k, v in result["per_label"].items()],
        "",
        "## Dangerous misses (human found a problem, evaluator said supported)",
        "",
    ]
    if result["dangerous_misses"]:
        lines += ["| SOP | Model | Run | Item | Draft text | Human |", "|---|---|---|---|---|---|"]
        lines += [f"| {r['sop']} | {r['model']} | {r['repeat']} | {r['draft_item_id']} | {r['draft_text']} | {r['human']} |"
                  for r in result["dangerous_misses"]]
    else:
        lines.append("None.")
    lines += ["", "## Omissions the evaluator missed", ""]
    if result["missed_omissions"]:
        lines += ["| SOP | Model | Run | Source item | Text |", "|---|---|---|---|---|"]
        lines += [f"| {o['run'][0]} | {o['run'][1]} | {o['run'][2]} | {o['item_id']} | {o['text']} |"
                  for o in result["missed_omissions"]]
    else:
        lines.append("None.")
    out = csv_path.with_name(csv_path.stem + "_agreement.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
    rows = read_csv(csv_path)
    if rows and "label_a" in rows[0]:
        base = csv_path.name.removesuffix("_annotation.csv")
        result = analyse_draft_items(rows, read_csv(csv_path.with_name(f"{base}_auto_labels.csv")),
                                     read_csv(csv_path.with_name(f"{base}_source_items.csv")))
        if not result["judged"]:
            sys.exit("No human labels yet. Fill label_a / source_item_a and label_b / source_item_b first.")
        print(f"kappa={result['kappa']} problem_recall={result['problem_recall']} "
              f"dangerous_misses={len(result['dangerous_misses'])} -> {write_draft_report(result, csv_path)}")
        return
    result = analyse(rows)
    if not result["judged"]:
        sys.exit("No human labels yet. Fill human_label_a / human_label_b first.")
    print(f"kappa={result['kappa']} problem_recall={result['problem_recall']} "
          f"dangerous_misses={len(result['dangerous_misses'])} -> {write_report(result, csv_path)}")


if __name__ == "__main__":
    main()
