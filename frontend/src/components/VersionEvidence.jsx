import { useState } from "react";
import { RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import { getDocumentVersions, getEvaluations, getVersionContent, runEvaluation, setFindingFeedback } from "../api.js";
import { useAuth, useNotice, useResource } from "../state.jsx";
import DiffView from "./DiffView.jsx";
import EvaluationReport from "./EvaluationReport.jsx";
import OriginalPdfPreview from "./OriginalPdfPreview.jsx";

const TABS = [["diff", "Compare with original"], ["text", "Full model output"]];

// The evidence a reviewer needs: the latest automated evaluation and the side-by-side
// comparison. "Show in comparison" on a finding switches to the comparison and highlights
// the line the finding quotes.
export default function VersionEvidence({ versionId, documentId, onEvaluated }) {
  const { show } = useNotice();
  const { user, can } = useAuth();
  const evaluations = useResource(() => getEvaluations(versionId), [versionId]);
  const content = useResource(() => getVersionContent(versionId), [versionId]);
  const [view, setView] = useState("diff");
  const [highlight, setHighlight] = useState(null);
  const [against, setAgainst] = useState("");  // "" = the original PDF text
  const [pdfPage, setPdfPage] = useState(null);  // null = preview closed
  const siblings = useResource(() => getDocumentVersions(documentId), [documentId]);
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

  // Reviewers label each finding; the labels become benchmark data (evaluation/export_finding_feedback.py).
  async function saveVerdict(index, verdict) {
    try {
      await setFindingFeedback(evaluation.id, index, verdict);
      evaluations.reload();
    } catch (error) {
      show(`Could not save your verdict: ${error.message}`, "error");
    }
  }

  function findingVerdict(finding, index) {
    if (!can("reviewer") || !evaluation?.id) return null;
    const mine = finding.feedback?.find((item) => item.user === user.username)?.verdict;
    const others = (finding.feedback || []).filter((item) => item.user !== user.username);
    return <>
      <button className="text-button" aria-pressed={mine === "true_problem"} onClick={() => saveVerdict(index, "true_problem")}><ThumbsUp size={14} /> True problem</button>
      <button className="text-button" aria-pressed={mine === "false_alarm"} onClick={() => saveVerdict(index, "false_alarm")}><ThumbsDown size={14} /> False alarm</button>
      {others.length > 0 && <small className="verdict-note">{others.map((item) => `${item.user}: ${item.verdict.replace("_", " ")}`).join(" · ")}</small>}
    </>;
  }

  function showInComparison(finding) {
    setView("diff");
    setAgainst("");  // finding line numbers refer to the original
    if (finding.source_page) setPdfPage(finding.source_page);
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
        <EvaluationReport evaluation={evaluation} onShowInComparison={showInComparison} renderActions={findingVerdict} />
      </section>

      <section className="panel" aria-label="Draft">
        <div className="view-tabs" role="tablist" aria-label="Draft view" onKeyDown={onTabKeyDown}>
          {TABS.map(([tab, label]) => (
            <button key={tab} id={`tab-${tab}`} role="tab" aria-selected={view === tab} aria-controls={`tabpanel-${tab}`} tabIndex={view === tab ? 0 : -1}
              className={view === tab ? "active" : ""} onClick={() => setView(tab)}>{label}</button>
          ))}
        </div>
        <div className="compare-bar">
          <label className="field-label" htmlFor="compare-with">Compare with</label>
          <select id="compare-with" className="form-input" value={against} onChange={(event) => { setAgainst(event.target.value); setView("diff"); }}>
            <option value="">Original PDF</option>
            {(siblings.data || []).filter((other) => other.id !== versionId).map((other) => (
              <option key={other.id} value={other.id}>Version {other.version_number}</option>
            ))}
          </select>
          <button className="btn btn-secondary" aria-expanded={pdfPage !== null} onClick={() => setPdfPage(pdfPage === null ? 1 : null)}>{pdfPage === null ? "Show original PDF" : "Hide original PDF"}</button>
        </div>
        {pdfPage !== null && <OriginalPdfPreview documentId={documentId} page={pdfPage} />}
        <div role="tabpanel" id={`tabpanel-${view}`} aria-labelledby={`tab-${view}`} tabIndex={0}>
          {/* key remounts the diff per comparison, so it never shows a previous result or error */}
          {view === "diff"
            ? <DiffView key={`${versionId}-${against}`} versionId={versionId} against={against} highlight={against ? null : highlight} />
            : <pre className="draft-output">{content.data ?? (content.error ? `Could not load: ${content.error.message}` : "Loading version content...")}</pre>}
        </div>
      </section>
    </>
  );
}
