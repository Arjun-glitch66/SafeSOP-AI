import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { getVersionDiff } from "../api.js";

const LABELS = { equal: "Unchanged", replace: "Changed", delete: "Removed from draft", insert: "Added in draft" };
// Changes are marked with a symbol and spoken text, never by colour alone.
const MARKERS = { original: ["−", "Removed: "], draft: ["+", "Added: "] };

const lineId = (side, line) => `diff-${side}-${line}`;

// Side-by-side original vs draft. Source warning lines are marked so a reviewer
// can see at a glance whether each one survived. Every line has an id built from the
// same 1-based numbering the evaluator uses, so a finding can point at it (`highlight`).
export default function DiffView({ versionId, against = "", highlight }) {
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getVersionDiff(versionId, against)
      .then((result) => { if (!cancelled) setDiff(result); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [versionId, against]);

  useEffect(() => {
    if (!diff || !highlight) return;
    const element = document.getElementById(lineId(highlight.side, highlight.line));
    if (!element) return;
    element.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    element.focus({ preventScroll: true });
  }, [diff, highlight]);

  if (error) return <p className="small-note">Could not load the comparison: {error}</p>;
  if (!diff) return <p className="small-note">Loading comparison…</p>;

  const warnings = new Set(diff.source_warnings);
  const line = (text, side, number, changed) => {
    const highlighted = highlight?.side === side && highlight?.line === number;
    return (
      <div key={`${side}-${number}`} id={lineId(side, number)} tabIndex={-1}
        className={`diff-line ${side === "original" && warnings.has(text) ? "diff-warning" : ""} ${highlighted ? "diff-highlight" : ""}`}>
        <span className="diff-marker" aria-hidden="true">{changed ? MARKERS[side][0] : ""}</span>
        {changed && <span className="sr-only">{MARKERS[side][1]}</span>}
        {highlighted && <span className="sr-only">Line referenced by the selected finding: </span>}
        {side === "original" && warnings.has(text) && <AlertTriangle size={13} aria-label="Source warning" />}
        <span className="diff-number" aria-hidden="true">{number}</span>
        <span>{text}</span>
      </div>
    );
  };

  return (
    <div className="diff-view" role="table" aria-label="Original compared with draft">
      <div className="diff-row diff-head" role="row">
        <div role="columnheader">{diff.left_label || "Original PDF text"}</div>
        <div role="columnheader">Generated draft · {Math.round(diff.similarity * 100)}% similar</div>
      </div>
      {diff.blocks.map((block, index) => (
        <div key={index} className={`diff-row diff-${block.tag}`} role="row" title={LABELS[block.tag]}>
          <div role="cell">{block.original.map((text, i) => line(text, "original", block.original_start + i, block.tag !== "equal"))}</div>
          <div role="cell">{block.draft.map((text, i) => line(text, "draft", block.draft_start + i, block.tag !== "equal"))}</div>
        </div>
      ))}
    </div>
  );
}
