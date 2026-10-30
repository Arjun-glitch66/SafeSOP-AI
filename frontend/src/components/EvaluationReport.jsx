import { AlertTriangle, FileSearch, FlaskConical, ShieldAlert, Workflow } from "lucide-react";
import { Badge, MetricCard } from "./ui.jsx";
import { evaluationLabel, percent, severityTone } from "./labels.js";

export default function EvaluationReport({ evaluation }) {
  if (!evaluation) return null;
  if (evaluation.status === "error" || !evaluation.metrics) {
    return <div className="notice-banner"><ShieldAlert size={20} /><div><strong>Automated evaluation did not run</strong><p>{evaluation.message}</p></div></div>;
  }
  const m = evaluation.metrics;
  return (
    <>
      <div className="metrics-grid">
        <MetricCard label="Warning recall" value={percent(m.warning_recall)} note={`${m.source_warnings} source warnings`} icon={AlertTriangle} tone="amber" />
        <MetricCard label="Unsupported instructions" value={percent(m.unsupported_instruction_rate)} note={`${m.unsupported_values} unsupported value(s)`} icon={FileSearch} tone="red" />
        <MetricCard label="Step-order integrity" value={percent(m.order_integrity)} note={`${m.omitted_steps} omitted · ${m.duplicated_steps} duplicated · ${m.conflicting_instructions} conflicting`} icon={Workflow} tone="purple" />
        <MetricCard label="Automated status" value={evaluationLabel[evaluation.status]} note={evaluation.evaluator_version} icon={FlaskConical} tone="blue" />
      </div>
      {evaluation.findings.length === 0 && <p className="small-note">No automated rule fired. This is not safety approval.</p>}
      {evaluation.findings.map((finding, index) => (
        <div className="finding-row" key={index}>
          <div className={`finding-icon finding-${severityTone[finding.severity]}`}><AlertTriangle size={18} /></div>
          <div className="row-main">
            <strong>{finding.type.replaceAll("_", " ")}</strong>
            <span>{finding.detail}</span>
            {finding.source && <span>Source{finding.source_line ? ` (line ${finding.source_line})` : ""}: <span className="quote">“{finding.source}”</span></span>}
            {finding.draft && <span>Draft{finding.draft_line ? ` (line ${finding.draft_line})` : ""}: <span className="quote">“{finding.draft}”</span></span>}
            {finding.evidence && <span>Evidence: {finding.evidence}</span>}
            {finding.values && <span>Values: {finding.values.join(", ")}</span>}
            {finding.pairs && <span>{finding.pairs.length} step pair(s) out of order, e.g. “{finding.pairs[0].before}” should come before “{finding.pairs[0].after}”</span>}
          </div>
          <Badge tone={severityTone[finding.severity]}>{finding.severity}</Badge>
        </div>
      ))}
    </>
  );
}
