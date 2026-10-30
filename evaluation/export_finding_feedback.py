"""
Turn reviewers' "true problem" / "false alarm" verdicts on automated findings into labelled rows.

    .venv\\Scripts\\python evaluation\\export_finding_feedback.py [--db data\\safesop.db] [--out results\\finding_feedback_labels.csv]

One row per finding that at least one reviewer labelled. `label` is the verdict when every
reviewer agrees, else `disputed` (resolve by discussion before using it, as in docs/BENCHMARK.md).
These rows measure the evaluator's precision on real drafts: a `false_alarm` is a false
positive. They cannot measure recall (problems the evaluator never flagged have no finding to
label); that still needs the EXP-003 draft-item annotation.
"""
import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIELDS = ["version_id", "document_id", "evaluation_id", "evaluator_version", "model", "prompt_version",
          "source_sha256", "finding_index", "finding_type", "severity", "source", "draft", "source_line",
          "draft_line", "verdicts", "label"]


def export(db_path, out_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT f.evaluation_id, f.finding_index, f.verdict, f.user, e.findings_json, e.evaluator_version,
                  v.id AS version_id, v.document_id, v.model, v.prompt_version, d.sha256 AS source_sha256
           FROM finding_feedback f
           JOIN evaluations e ON e.id = f.evaluation_id
           JOIN versions v ON v.id = e.version_id
           JOIN documents d ON d.id = v.document_id
           ORDER BY v.created_at, f.evaluation_id, f.finding_index, f.user"""
    ).fetchall()
    connection.close()

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["evaluation_id"], row["finding_index"])].append(row)

    out_rows = []
    for (_, index), verdicts in grouped.items():
        first = verdicts[0]
        finding = json.loads(first["findings_json"])[index]
        labels = {row["verdict"] for row in verdicts}
        out_rows.append({
            "version_id": first["version_id"], "document_id": first["document_id"],
            "evaluation_id": first["evaluation_id"], "evaluator_version": first["evaluator_version"],
            "model": first["model"], "prompt_version": first["prompt_version"],
            "source_sha256": first["source_sha256"], "finding_index": index, "finding_type": finding["type"],
            "severity": finding["severity"], "source": finding.get("source") or "", "draft": finding.get("draft") or "",
            "source_line": finding.get("source_line") or "", "draft_line": finding.get("draft_line") or "",
            "verdicts": ";".join(f"{row['user']}:{row['verdict']}" for row in verdicts),
            "label": labels.pop() if len(labels) == 1 else "disputed",
        })

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    agreed = [row for row in out_rows if row["label"] != "disputed"]
    by_type = defaultdict(Counter)
    for row in agreed:
        by_type[row["finding_type"]][row["label"]] += 1
    return {
        "labelled_findings": len(out_rows),
        "disputed": len(out_rows) - len(agreed),
        # Share of agreed-on findings of each type that reviewers called a true problem.
        "precision_by_type": {kind: round(c["true_problem"] / sum(c.values()), 3) for kind, c in sorted(by_type.items())},
    }


def main():
    from app import config
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(config.DB_PATH))
    parser.add_argument("--out", default=str(ROOT / "results" / "finding_feedback_labels.csv"))
    args = parser.parse_args()
    summary = export(args.db, args.out)
    print(f"{summary['labelled_findings']} labelled findings ({summary['disputed']} disputed) -> {args.out}")
    for kind, precision in summary["precision_by_type"].items():
        print(f"  {kind}: precision {precision}")


if __name__ == "__main__":
    main()
