import { useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ArrowDownToLine, BookOpen, Check, CheckCircle2, FileClock, FileText, Files, History, ShieldCheck, Sparkles, Workflow, X } from "lucide-react";
import { createChangeRequest, downloadOriginal, followJob, generateRevision, getDocument, getDocumentVersions } from "../api.js";
import { Badge, EmptyState } from "../components/ui.jsx";
import { evaluationLabel, evaluationTone, statusLabel, statusTone } from "../components/labels.js";
import { useAuth, useBackend, useNotice, useResource, useTitle } from "../state.jsx";

const SCOPES = [
  { name: "Full document", value: "full", desc: "Complete revised SOP", icon: Files },
  { name: "Selected page", value: "page", desc: "One page only (text, not PDF layout)", icon: FileText },
  { name: "Selected section", desc: "Not supported yet", icon: BookOpen, disabled: true },
  { name: "Selected step", desc: "Not supported yet", icon: Workflow, disabled: true },
];

export default function DocumentPage() {
  const { documentId } = useParams();
  const document = useResource(() => getDocument(documentId), [documentId]);
  const versions = useResource(() => getDocumentVersions(documentId), [documentId]);
  useTitle(document.data?.filename || "Document");
  const { can } = useAuth();
  const { show } = useNotice();
  const latest = versions.data?.[0];

  if (document.error) return <EmptyState icon={FileText} title="Document not available" text={document.error.message} action={<Link className="btn btn-primary" to="/documents">Back to documents</Link>} />;
  const doc = document.data;

  return (
    <>
      <section className="title-block" aria-labelledby="document-title">
        <div className="title-block-head">
          <div>
            <p className="title-block-kicker">Source document</p>
            <h1 id="document-title">{doc ? doc.filename.replace(/\.pdf$/i, "").replaceAll("_", " ") : "Loading…"}</h1>
            <p>Every draft is generated from this original PDF and needs a qualified reviewer's sign-off before use.</p>
          </div>
          {doc && <div className="action-row"><button className="btn btn-secondary" onClick={() => downloadOriginal(doc.id, doc.filename).catch((error) => show(`Download failed: ${error.message}`, "error"))}><ArrowDownToLine size={16} /> Original PDF</button></div>}
        </div>
        <dl className="title-block-fields">
          <div><dt>Latest revision</dt><dd>{latest ? `v${latest.version_number}` : "None"}</dd></div>
          <div><dt>Automated check</dt><dd>{latest?.evaluation_status ? evaluationLabel[latest.evaluation_status] : "Not run"}</dd></div>
          <div><dt>Review status</dt><dd>{statusLabel(latest?.status)}</dd></div>
          <div><dt>Versions</dt><dd>{versions.data?.length ?? "…"}</dd></div>
          <div><dt>Pages</dt><dd>{doc?.page_count ?? "Unknown"}</dd></div>
          <div><dt>Checklist</dt><dd>{doc?.document_type ? doc.document_type.replaceAll("_", " ") : "None"}</dd></div>
        </dl>
      </section>

      {can("author") && doc && <RequestForm doc={doc} onGenerated={versions.reload} />}
      <VersionRegister versions={versions} />
    </>
  );
}

function RequestForm({ doc, onGenerated }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { online } = useBackend();
  const { show } = useNotice();
  // "Regenerate from original" on a version page arrives here with that version as the parent.
  const parentFromVersion = location.state?.parent;
  const [parent, setParent] = useState(parentFromVersion || null);
  const [scope, setScope] = useState(parentFromVersion?.scope === "page" ? "page" : "full");
  const [targetPage, setTargetPage] = useState(String(parentFromVersion?.target_page || 1));
  const [changeRequest, setChangeRequest] = useState(parentFromVersion?.change_request || "");
  const [saved, setSaved] = useState(null);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [stage, setStage] = useState("");
  const controller = useRef(null);

  function ready() {
    if (!changeRequest.trim()) { show("Enter the requested process change.", "error"); return false; }
    const page = Number(targetPage);
    if (scope === "page" && (!(page >= 1) || (doc.page_count && page > doc.page_count))) {
      show(`Enter a target page between 1 and ${doc.page_count || "the last page"}.`, "error");
      return false;
    }
    return true;
  }

  async function generate(requestId = null) {
    if (!requestId && !ready()) return;
    controller.current = new AbortController();
    setGenerating(true);
    setStage("Sending the request");
    try {
      // The backend always reads the immutable original PDF, never a previous draft.
      // It answers at once with a job; the model call runs in the background.
      const accepted = await generateRevision(doc.id, {
        description: changeRequest.trim(), scope, targetPage: Number(targetPage),
        parentVersionId: parent?.id, requestId,
      });
      setStage(accepted.stage_text);
      const job = await followJob(accepted.job_id, (progress) => setStage(progress.stage_text), controller.current.signal);
      if (job.status !== "succeeded") throw new Error(job.detail || "Generation failed.");
      const result = job.result;
      show(`Draft saved as version ${result.version_number}. Automated check: ${evaluationLabel[result.safety_evaluation?.status] || "not run"}.`);
      navigate(`/versions/${result.version_id}`);
    } catch (error) {
      if (error.name === "AbortError") {
        show("Stopped watching. The draft is still being generated and will appear in the revision register when it is ready.");
        window.setTimeout(onGenerated, 15000);
      } else {
        show(`Generation failed: ${error.message}`, "error");
      }
    } finally {
      setGenerating(false);
      controller.current = null;
    }
  }

  async function saveOnly() {
    if (!ready()) return;
    setSaving(true);
    try {
      setSaved(await createChangeRequest(doc.id, changeRequest.trim(), scope, Number(targetPage)));
      show("Change request saved. AI generation has not run yet.");
    } catch (error) {
      show(`Could not save request: ${error.message}`, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="request-heading">
      <div className="panel-heading"><div><h2 id="request-heading">New revision</h2><p>Describe the engineer-approved process change. The draft is always built from the original PDF.</p></div><Badge tone="amber" dot>Draft workspace</Badge></div>

      <span className="field-label" id="scope-label">Output scope</span>
      <div className="scope-options" role="radiogroup" aria-labelledby="scope-label">
        {SCOPES.map((item) => (
          <button key={item.name} role="radio" aria-checked={scope === item.value} className={`scope-option ${scope === item.value ? "selected" : ""}`} disabled={item.disabled || generating} onClick={() => setScope(item.value)}>
            <item.icon size={19} /><span><strong>{item.name}</strong><small>{item.desc}</small></span>{scope === item.value && <CheckCircle2 size={16} className="scope-check" />}
          </button>
        ))}
      </div>

      {scope === "page" && <>
        <label className="field-label" htmlFor="target-page">Target page{doc.page_count ? ` (1–${doc.page_count})` : ""}</label>
        <input id="target-page" className="form-input" type="number" min="1" max={doc.page_count || undefined} value={targetPage} onChange={(event) => setTargetPage(event.target.value)} />
      </>}

      <label className="field-label" htmlFor="change-request">Requested change <span className="required">*</span></label>
      <textarea id="change-request" className="form-textarea" maxLength={2000} value={changeRequest} onChange={(event) => setChangeRequest(event.target.value)} placeholder="Describe what changed, why it changed, and which safety requirements must remain unchanged..." rows={6} />

      {parent && <div className="form-note"><History size={16} /><span>Regenerating from version {parent.version_number}. The new draft is still generated from the <strong>original PDF</strong>; version {parent.version_number} is only recorded as its parent. <button className="text-button" onClick={() => setParent(null)}>Clear</button></span></div>}
      <div className="form-note"><ShieldCheck size={16} /><span>Safety warnings and critical prerequisites must be preserved or explicitly flagged for qualified review.</span></div>

      {generating ? (
        <div className="generation-progress" aria-live="polite">
          <div><strong>{stage}…</strong><p>Usually 5–30 seconds. The draft is checked automatically as soon as it arrives.</p></div>
          <div className="progress-indeterminate"><span /></div>
          <button className="btn btn-secondary" onClick={() => controller.current?.abort()}><X size={16} /> Stop watching</button>
        </div>
      ) : <>
        <button className="btn btn-primary btn-full" disabled={!online} onClick={() => generate()}><Sparkles size={16} /> Generate revised draft</button>
        <button className="btn btn-secondary btn-full btn-stacked" disabled={saving || !online} onClick={saveOnly}><Check size={16} /> {saving ? "Saving request..." : "Save request only (no generation)"}</button>
      </>}

      {saved && !generating && <div className="request-summary">
        <p><strong>Saved request:</strong> {saved.scope === "page" ? `page ${saved.target_page}` : "full document"} · {saved.description}</p>
        <button className="btn btn-primary" disabled={!online} onClick={() => generate(saved.id)}><Sparkles size={16} /> Generate draft from this saved request</button>
      </div>}
    </section>
  );
}

function VersionRegister({ versions }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const rows = (versions.data || []).filter((version) =>
    `v${version.version_number} ${version.status} ${version.change_request || ""}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <section className="panel" aria-labelledby="register-heading">
      <div className="panel-heading"><div><h2 id="register-heading">Revision register</h2><p>Every generated draft of this SOP, newest first.</p></div><input className="form-input register-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search versions..." aria-label="Search versions" /></div>
      {versions.error && <p className="form-error" role="alert">Could not load versions: {versions.error.message}</p>}
      {versions.data?.length === 0 ? <EmptyState icon={FileClock} title="No generated versions yet" text="Describe a change above to generate the first draft." /> :
        <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Version</th><th>Change request</th><th>Created</th><th>Automated check</th><th>Review status</th></tr></thead>
          <tbody>{rows.map((version) => (
            <tr key={version.id} onClick={() => navigate(`/versions/${version.id}`)}>
              <td><Link to={`/versions/${version.id}`} className="table-doc" onClick={(event) => event.stopPropagation()}><span className="file-icon"><FileText size={18} /></span><span><strong>Version {version.version_number}</strong><small>{version.scope === "page" ? `Page ${version.target_page ?? "?"}` : "Full document"} · {version.characters} chars</small></span></Link></td>
              <td>{(version.change_request || "—").slice(0, 80)}{(version.change_request || "").length > 80 ? "…" : ""}</td>
              <td>{new Date(version.created_at).toLocaleString()}</td>
              <td><Badge tone={evaluationTone[version.evaluation_status] || "gray"}>{evaluationLabel[version.evaluation_status] || "Not run"}</Badge></td>
              <td><Badge tone={statusTone(version.status)} dot>{statusLabel(version.status)}</Badge></td>
            </tr>
          ))}</tbody>
        </table></div>}
    </section>
  );
}
