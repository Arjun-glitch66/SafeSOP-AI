import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { getEvaluations, getVersionContent, runEvaluation } from "../api.js";
import { useNotice, useResource } from "../state.jsx";
import DiffView from "./DiffView.jsx";
import EvaluationReport from "./EvaluationReport.jsx";

const TABS = [["diff", "Compare with original"], ["text", "Full model output"]];

// The evidence a reviewer needs: the latest automated evaluation and the side-by-side
// comparison. "Show in comparison" on a finding switches to the comparison and highlights
// the line the finding quotes.
export default function VersionEvidence({ versionId, onEvaluated }) {
  const { show } = useNotice();
  const evaluations = useResource(() => getEvaluations(versionId), [versionId]);
  const content = useResource(() => getVersionContent(versionId), [versionId]);
  const [view, setView] = useState("diff");
  const [highlight, setHighlight] = useState(null);
  const [evaluating, setEvaluating] = useState(false);
  const evaluation = evaluations.data?.[0] || null;

  async function rerun() {
    setEvaluating(true);
    try {
      const result = await runEvaluation(versionId);
      evaluations.reload();
      onEvaluated?.();
      // The API answers 200 with status "error" when the evaluator itself crashed.
      show(result.status === "error" ? result.message : "Automated checks re-run and saved.", result.status === "error" ? "error" : "success");
    } catch (error) {
      show(`Evaluation failed: ${error.message}`, "error");
    } finally {
      setEvaluating(false);
    }
  }

  function showInComparison(finding) {
    setView("diff");
    setHighlight(finding.draft_line ? { side: "draft", line: finding.draft_line, at: Date.now() }
      : { side: "original", line: finding.source_line, at: Date.now() });
  }

  // Arrow keys / Home / End move between tabs (WAI-ARIA tabs pattern, automatic activation).
  function onTabKeyDown(event) {
    const index = TABS.findIndex(([tab]) => tab === view);
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: TABS.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const [tab] = TABS[(next + TABS.length) % TABS.length];
    setView(tab);
    document.getElementById(`tab-${tab}`)?.focus();
  }

  return (
    <>
      <section className="panel" aria-labelledby="checks-heading">
        <div className="panel-heading">
          <div><h2 id="checks-heading">Automated checks</h2><p>{evaluation ? `Evaluated ${new Date(evaluation.created_at).toLocaleString()} with ${evaluation.evaluator_version}` : evaluations.loading ? "Loading…" : "This version has no saved evaluation yet."}</p></div>
          <button className="btn btn-secondary" disabled={evaluating} onClick={rerun}><RefreshCw size={16} /> {evaluating ? "Evaluating..." : "Re-run checks"}</button>
        </div>
        <EvaluationReport evaluation={evaluation} onShowInComparison={showInComparison} />
      </section>

      <section className="panel" aria-label="Draft">
        <div className="view-tabs" role="tablist" aria-label="Draft view" onKeyDown={onTabKeyDown}>
          {TABS.map(([tab, label]) => (
            <button key={tab} id={`tab-${tab}`} role="tab" aria-selected={view === tab} aria-controls={`tabpanel-${tab}`} tabIndex={view === tab ? 0 : -1}
              className={view === tab ? "active" : ""} onClick={() => setView(tab)}>{label}</button>
          ))}
        </div>
        <div role="tabpanel" id={`tabpanel-${view}`} aria-labelledby={`tab-${view}`} tabIndex={0}>
          {view === "diff"
            ? <DiffView key={versionId} versionId={versionId} highlight={highlight} />
            : <pre className="draft-output">{content.data ?? (content.error ? `Could not load: ${content.error.message}` : "Loading version content...")}</pre>}
        </div>
      </section>
    </>
  );
}
