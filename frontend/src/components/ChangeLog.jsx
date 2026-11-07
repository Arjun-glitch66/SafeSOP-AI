import { Badge } from "./ui.jsx";

const TONE = { modified: "amber", added: "blue", removed: "red", reworded: "amber" };

// Rows for every step or warning the model changed, with the model's stated reason.
export function changeRows(structured) {
  if (!structured) return [];
  const rows = (structured.steps || []).filter((step) => step.change_type !== "unchanged").map((step) => ({
    id: step.id, kind: step.change_type, from: (step.source_step_ids || []).join(", "), text: step.text, reason: step.reason,
  }));
  for (const warning of structured.warnings || []) {
    if (warning.source_warning_id && !warning.reason) continue;  // carried unchanged
    rows.push({ id: warning.id, kind: warning.source_warning_id ? "reworded" : "added", from: warning.source_warning_id || "",
      text: warning.text, reason: warning.reason });
  }
  for (const id of structured.removed_warning_ids || []) {
    rows.push({ id, kind: "removed", from: id, text: "Warning removed", reason: "See the change summary. A qualified reviewer must confirm the hazard no longer exists." });
  }
  return rows;
}

// structuredJson: versions.structured_json (prompt v3+). Older drafts have no structure; v3/v4 drafts have no reasons.
export default function ChangeLog({ structuredJson }) {
  let structured = null;
  try { structured = structuredJson ? JSON.parse(structuredJson) : null; } catch { structured = null; }
  const rows = changeRows(structured);
  const hasReasons = Boolean(structured && [...(structured.steps || []), ...(structured.warnings || [])].some((item) => "reason" in item));

  return (
    <section className="panel" aria-labelledby="changelog-heading">
      <div className="panel-heading"><div><h2 id="changelog-heading">What changed and why</h2><p>The model's own account of each change, citing the source item it came from (S = step, W = warning). Reasons are explanations to check, not verified facts.</p></div></div>
      {!structured && <p className="small-note">This version was generated before structured output, so there is no per-change record. Use the comparison below.</p>}
      {structured && !hasReasons && <p className="small-note">This version was generated before prompt v5, so changes have no stated reasons.</p>}
      {structured && rows.length === 0 && <p className="small-note">The model reports no changed steps or warnings.</p>}
      {rows.length > 0 && <div className="table-wrap"><table className="data-table text-table">
        <thead><tr><th>Item</th><th>Change</th><th>From</th><th>Text</th><th>Reason</th></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={`${row.id}-${row.kind}`}>
            <td>{row.id}</td>
            <td><Badge tone={TONE[row.kind] || "gray"}>{row.kind}</Badge></td>
            <td>{row.from || "new"}</td>
            <td className="wrap">{row.text}</td>
            <td className="wrap">{hasReasons ? (row.reason?.trim() || <strong className="form-error">No reason given</strong>) : "—"}</td>
          </tr>
        ))}</tbody>
      </table></div>}
    </section>
  );
}
