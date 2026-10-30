import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { getVersionDiff } from "../api.js";

const LABELS = { equal: "Unchanged", replace: "Changed", delete: "Removed from draft", insert: "Added in draft" };
// Changes are marked with a symbol and spoken text, never by colour alone.
const MARKERS = { original: ["−", "Removed: "], draft: ["+", "Added: "] };

// Side-by-side original vs draft. Source warning lines are marked so a reviewer
// can see at a glance whether each one survived.
export default function DiffView({ versionId }) {
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getVersionDiff(versionId)
      .then((result) => { if (!cancelled) setDiff(result); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [versionId]);

  if (error) return <p className="small-note">Could not load the comparison: {error}</p>;
  if (!diff) return <p className="small-note">Loading comparison…</p>;

  const warnings = new Set(diff.source_warnings);
  const line = (text, side, index, changed) => (
    <div key={`${side}-${index}`} className={`diff-line ${side === "original" && warnings.has(text) ? "diff-warning" : ""}`}>
      <span className="diff-marker" aria-hidden="true">{changed ? MARKERS[side][0] : ""}</span>
      {changed && <span className="sr-only">{MARKERS[side][1]}</span>}
      {side === "original" && warnings.has(text) && <AlertTriangle size={13} aria-label="Source warning" />}
      <span>{text}</span>
    </div>
  );

  return (
    <div className="diff-view" role="table" aria-label="Original compared with draft">
      <div className="diff-row diff-head" role="row">
        <div role="columnheader">Original PDF text</div>
        <div role="columnheader">Generated draft · {Math.round(diff.similarity * 100)}% similar</div>
      </div>
      {diff.blocks.map((block, index) => (
        <div key={index} className={`diff-row diff-${block.tag}`} role="row" title={LABELS[block.tag]}>
          <div role="cell">{block.original.map((text, i) => line(text, "original", i, block.tag !== "equal"))}</div>
          <div role="cell">{block.draft.map((text, i) => line(text, "draft", i, block.tag !== "equal"))}</div>
        </div>
      ))}
    </div>
  );
}
