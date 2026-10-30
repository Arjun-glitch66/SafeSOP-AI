import { RefreshCw } from "lucide-react";
import EvaluationReport from "../components/EvaluationReport.jsx";
import { Badge } from "../components/ui.jsx";

const FRAMEWORK = [
  ["Warning preservation", "Each source warning must appear in the draft (token containment ≥ 0.8). 0.5–0.8 is flagged as altered for review.", "Critical"],
  ["Unsupported instructions and values", "Draft steps must be supported by the source or the change request. New numbers, and known numbers with a different unit, are flagged.", "Critical"],
  ["Step-order integrity", "Share of source step pairs that keep their relative order in the draft.", "Critical"],
  ["Omitted, altered, duplicated and conflicting steps", "Source steps are matched to draft steps. Removed steps, wording changes, near-duplicates, negation flips and opposite words (on/off, open/close) are reported.", "High"],
  ["Uncertain cases", "Borderline matches, missing sections or undetectable structure give 'needs review', never a pass.", "Review"],
];

export default function SafetyQuality({ app }) {
  const { file, selectedVersion, versionEvaluation, evaluating, handleRunEvaluation, setActivePage, evaluatorVersion } = app;

  return (
    <>
      <div className="page-intro"><div><h1>Safety & quality</h1><p>Automated checks compare each draft with the original PDF. They flag problems for a reviewer; they never approve a draft.</p></div><Badge tone="amber" dot>Human review required</Badge></div>
      <section className="panel">
        <div className="panel-heading">
          <div><h3>{selectedVersion ? `Version ${selectedVersion.version_number} · ${file?.name}` : "No version selected"}</h3><p>{versionEvaluation ? `Evaluated ${new Date(versionEvaluation.created_at).toLocaleString()} with ${versionEvaluation.evaluator_version}` : selectedVersion ? "This version has no saved evaluation yet." : "Generate a draft, or open a version in Version History."}</p></div>
          {selectedVersion ? <button className="btn btn-secondary" disabled={evaluating} onClick={handleRunEvaluation}><RefreshCw size={16} /> {evaluating ? "Evaluating..." : "Re-run checks"}</button>
            : <button className="btn btn-primary" onClick={() => setActivePage("Version History")}>Choose version</button>}
        </div>
        <EvaluationReport evaluation={versionEvaluation} />
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h3>Evaluation framework</h3><p>What the automated checks measure. Full definitions: research_logbook/EVALUATION_FRAMEWORK.md</p></div><Badge tone="blue">{evaluatorVersion || "evaluator"}</Badge></div>
        {FRAMEWORK.map(([title, text, level]) => (
          <div className="framework-row" key={title}><div className="row-main"><strong>{title}</strong><span>{text}</span></div><Badge tone={level === "Review" ? "amber" : "red"}>{level}</Badge></div>
        ))}
        <div className="panel-footnote">The checks compare words, not meaning: correct paraphrases may be flagged for review, and opposite words outside the built-in list are not detected. Automated checks never replace qualified human approval.</div>
      </section>
    </>
  );
}
