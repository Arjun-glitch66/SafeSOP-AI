import {
  Activity, ArrowDownToLine, BookOpen, Check, CheckCircle2, FilePlus2, FileText, Files,
  History, Settings, ShieldAlert, ShieldCheck, Sparkles, Workflow,
} from "lucide-react";
import EvaluationReport from "../components/EvaluationReport.jsx";
import { Badge } from "../components/ui.jsx";
import { evaluationLabel } from "../components/labels.js";
import { versionDownloadUrl } from "../api.js";

const SCOPES = [
  { name: "Full document", desc: "Complete revised SOP", icon: Files },
  { name: "Selected page", desc: "One page only (text, not PDF layout)", icon: FileText },
  { name: "Selected section", desc: "Not supported yet", icon: BookOpen, disabled: true },
  { name: "Selected step", desc: "Not supported yet", icon: Workflow, disabled: true },
];

export default function RevisionStudio({ app }) {
  const {
    file, pageCount, scope, setScope, targetPage, setTargetPage, changeRequest, setChangeRequest,
    parentVersion, setParentVersion, generating, savingRequest, backendOnline,
    handleGenerate, handleSaveRequest, showRequest, savedRequests, generated, setActivePage,
  } = app;

  const done = [Boolean(file), Boolean(changeRequest.trim()), Boolean(generated), false];
  const count = done.filter(Boolean).length;

  return (
    <>
      <div className="page-intro"><div><h2>Revision studio</h2><p>Describe the process change and choose what to regenerate. The draft is always built from the original PDF.</p></div><Badge tone="amber" dot>Draft workspace</Badge></div>

      <div className="content-grid revision-grid">
        <section className="panel">
          <div className="panel-heading"><div><h3>Change request</h3><p>Describe the engineer-approved process change.</p></div><FilePlus2 size={19} className="subtle-icon" /></div>
          <span className="field-label">Source document</span>
          <div className="source-select"><FileText size={18} /><div><strong>{file ? file.name : "No source selected"}</strong><span>{file ? `Original stored in backend${pageCount ? ` · ${pageCount} page${pageCount === 1 ? "" : "s"}` : ""}` : "Upload or choose a saved PDF in Document Center first"}</span></div><button className="text-button" onClick={() => setActivePage("Documents")}>Choose</button></div>

          <span className="field-label" id="scope-label">Output scope</span>
          <div className="scope-options" role="radiogroup" aria-labelledby="scope-label">
            {SCOPES.map((item) => (
              <button key={item.name} role="radio" aria-checked={scope === item.name} className={`scope-option ${scope === item.name ? "selected" : ""}`} disabled={item.disabled} onClick={() => setScope(item.name)}>
                <item.icon size={19} /><span><strong>{item.name}</strong><small>{item.desc}</small></span>{scope === item.name && <CheckCircle2 size={16} className="scope-check" />}
              </button>
            ))}
          </div>

          {scope === "Selected page" && <>
            <label className="field-label" htmlFor="target-page">Target page{pageCount ? ` (1–${pageCount})` : ""}</label>
            <input id="target-page" className="form-input" type="number" min="1" max={pageCount || undefined} value={targetPage} onChange={(event) => setTargetPage(event.target.value)} />
          </>}

          <label className="field-label" htmlFor="change-request">Requested change <span className="required">*</span></label>
          <textarea id="change-request" className="form-textarea" value={changeRequest} onChange={(event) => setChangeRequest(event.target.value)} placeholder="Describe what changed, why it changed, and which safety requirements must remain unchanged..." rows={6} />

          {parentVersion && <div className="form-note"><History size={16} /><span>Regenerating from version {parentVersion.version_number}. The new draft is still generated from the <strong>original PDF</strong>; version {parentVersion.version_number} is only recorded as its parent. <button className="text-button" onClick={() => setParentVersion(null)}>Clear</button></span></div>}
          <div className="form-note"><ShieldCheck size={16} /><span>Safety warnings and critical prerequisites must be preserved or explicitly flagged for qualified review.</span></div>
          <button className="btn btn-primary btn-full" disabled={generating || !backendOnline} onClick={handleGenerate}><Sparkles size={16} /> {generating ? "Generating draft with Gemini..." : "Generate revised draft"}</button>
          <button className="btn btn-secondary btn-full btn-stacked" disabled={savingRequest || generating || !backendOnline} onClick={handleSaveRequest}><Check size={16} /> {savingRequest ? "Saving request..." : "Save request only (no generation)"}</button>
        </section>

        <div className="stack">
          <section className="panel">
            <div className="panel-heading"><div><h3>Request progress</h3><p>Preparation checklist</p></div><Activity size={18} className="subtle-icon" /></div>
            <div className="progress-count">{count}<span> / 4 steps</span></div>
            <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={4} aria-valuenow={count}><span style={{ width: `${count * 25}%` }} /></div>
            {["Source document selected", "Change request described", "Draft generated and auto-checked", "Qualified human review"].map((label, index) => (
              <div className="checklist-row" key={label}><span className={`check-circle ${done[index] ? "complete" : ""}`}>{done[index] ? <Check size={12} /> : index + 1}</span><span>{label}</span></div>
            ))}
          </section>
          <section className="panel">
            <div className="panel-heading"><div><h3>Generation settings</h3><p>Pipeline configuration</p></div><Settings size={18} className="subtle-icon" /></div>
            <div className="setting-row"><span>Original as source of truth</span><Badge tone="green">Required</Badge></div>
            <div className="setting-row"><span>Retain earlier versions</span><Badge tone="green">Enabled</Badge></div>
            <div className="setting-row"><span>Automatic safety approval</span><Badge tone="red">Disabled</Badge></div>
            <p className="small-note">Every generation reads the original uploaded PDF, never an earlier draft. Automated safety checks run on every draft; they never approve it.</p>
          </section>
        </div>
      </div>

      {generating && <section className="panel request-summary" aria-live="polite">
        <div className="panel-heading"><div><h3>Generating draft…</h3><p>Gemini usually takes 5–30 seconds. The draft is checked automatically as soon as it arrives.</p></div><Sparkles size={18} className="subtle-icon" /></div>
        <div className="progress-indeterminate"><span /></div>
      </section>}

      {showRequest && !generated && !generating && <section className="panel request-summary"><div className="panel-heading"><div><h3>Saved request preview</h3><p>Saved change request. AI generation has not run yet.</p></div><Badge tone="blue">Prepared</Badge></div><p><strong>Scope:</strong> {scope}</p><p><strong>Change:</strong> {changeRequest}</p>{savedRequests[0] && <p><strong>Request ID:</strong> {savedRequests[0].id}</p>}<button className="btn btn-primary" onClick={handleGenerate}><Sparkles size={16} /> Generate draft from this request</button></section>}

      {generated && <section className="panel request-summary">
        <div className="panel-heading"><div><h3>Generated draft · Version {generated.version_number}</h3><p>{generated.model} · prompt {generated.prompt_version} · temperature {generated.temperature ?? "default"} · {generated.input_tokens ?? "?"} input / {generated.output_tokens ?? "?"} output tokens · {new Date(generated.created_at).toLocaleString()}</p></div><Badge tone="amber" dot>Draft · Not approved</Badge></div>
        <div className="notice-banner"><ShieldAlert size={20} /><div><strong>Not safety-approved · Automated check: {evaluationLabel[generated.safety_evaluation?.status] || "not run"}</strong><p>{generated.safety_evaluation?.message}</p></div></div>
        <EvaluationReport evaluation={generated.safety_evaluation} />
        <pre className="draft-output">{generated.content}</pre>
        <div className="action-row">
          <a className="btn btn-primary" href={versionDownloadUrl(generated.version_id, "pdf")}><ArrowDownToLine size={16} /> Download draft (PDF)</a>
          <a className="btn btn-secondary" href={versionDownloadUrl(generated.version_id)}><ArrowDownToLine size={16} /> Text (.txt)</a>
          <button className="btn btn-secondary" onClick={() => setActivePage("Version History")}><History size={16} /> Compare and review</button>
        </div>
      </section>}
    </>
  );
}
