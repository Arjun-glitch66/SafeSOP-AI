import { useState } from "react";
import { ArrowDownToLine, CheckCircle2, FileClock, FileText, History, RefreshCw, Search, X } from "lucide-react";
import DiffView from "../components/DiffView.jsx";
import { Badge, EmptyState } from "../components/ui.jsx";
import { evaluationLabel, evaluationTone, statusLabel, statusTone } from "../components/labels.js";
import { originalDownloadUrl, versionDownloadUrl } from "../api.js";

export default function VersionHistory({ app }) {
  const {
    file, versions, selectedVersion, openVersion, versionEvaluation, versionContent, reviews,
    reviewer, setReviewer, reviewFeedback, setReviewFeedback, submittingReview, handleReview,
    startRegeneration, setActivePage, query, setQuery,
  } = app;
  const [view, setView] = useState("diff");
  const item = selectedVersion;

  if (!file) {
    return (
      <>
        <Intro />
        <section className="panel"><EmptyState icon={History} title="No source document selected" text="Choose a saved PDF in the Document Center to see its generated versions." action={<button className="btn btn-primary" onClick={() => setActivePage("Documents")}>Choose document</button>} /></section>
      </>
    );
  }

  const filtered = versions.filter((version) =>
    `v${version.version_number} ${version.status} ${version.change_request || ""}`.toLowerCase().includes(query.toLowerCase()));
  const parentNumber = item?.parent_version_id && versions.find((v) => v.id === item.parent_version_id)?.version_number;
  const counts = (severity) => versionEvaluation?.findings?.filter((f) => f.severity === severity).length ?? 0;

  return (
    <>
      <Intro />
      <section className="panel">
        <div className="panel-heading"><div><h3>Revision register</h3><p>{file.name} · original stored unchanged · <a className="text-button" href={originalDownloadUrl(file.id)}>Download original PDF</a></p></div><div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search versions..." aria-label="Search versions" /></div></div>
        {versions.length === 0 ? <EmptyState icon={FileClock} title="No generated versions yet" text="Generate a draft in the Revision Studio. Each draft is saved as a new version." action={<button className="btn btn-primary" onClick={() => setActivePage("Revision Studio")}>Open Revision Studio</button>} /> :
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Version</th><th>Change request</th><th>Created</th><th>Automated check</th><th>Review status</th><th><span className="sr-only">Download</span></th></tr></thead>
            <tbody>{filtered.map((version) => (
              <tr key={version.id} className={item?.id === version.id ? "selected-row" : ""} onClick={() => openVersion(version.id)}
                tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") openVersion(version.id); }} aria-selected={item?.id === version.id}>
                <td><div className="table-doc"><span className="file-icon"><FileText size={18} /></span><span><strong>Version {version.version_number}</strong><small>{version.scope === "page" ? `Page ${version.target_page ?? "?"}` : "Full document"} · {version.characters} chars</small></span></div></td>
                <td>{(version.change_request || "—").slice(0, 80)}{(version.change_request || "").length > 80 ? "…" : ""}</td>
                <td>{new Date(version.created_at).toLocaleString()}</td>
                <td><Badge tone={evaluationTone[version.evaluation_status] || "gray"}>{evaluationLabel[version.evaluation_status] || "Not run"}</Badge></td>
                <td><Badge tone={statusTone(version.status)} dot>{statusLabel(version.status)}</Badge></td>
                <td><a className="icon-button" aria-label={`Download version ${version.version_number} as PDF`} href={versionDownloadUrl(version.id, "pdf")} onClick={(event) => event.stopPropagation()}><ArrowDownToLine size={16} /></a></td>
              </tr>
            ))}</tbody>
          </table></div>}
      </section>

      {item && <section className="panel">
        <div className="panel-heading">
          <div><h3>Version {item.version_number}</h3><p>Source: original PDF {file.name}{item.scope === "page" && item.target_page ? ` · page ${item.target_page}` : ""}{parentNumber ? ` · revises version ${parentNumber}` : ""} · {item.model || "model not recorded"}{item.prompt_version ? ` · prompt ${item.prompt_version}` : ""}{item.temperature != null ? ` · temperature ${item.temperature}` : ""}</p></div>
          <button className="btn btn-secondary" onClick={() => startRegeneration(item)}><RefreshCw size={16} /> Regenerate from original</button>
        </div>
        <div className="timeline">
          <div className="timeline-item"><span className="timeline-dot blue" /><div><strong>Draft created</strong><p>{item.change_request || "No change request recorded."}</p><small>{new Date(item.created_at).toLocaleString()}</small></div></div>
          <div className="timeline-item"><span className="timeline-dot amber" /><div><strong>Automated safety evaluation: {versionEvaluation ? evaluationLabel[versionEvaluation.status] : "not run"}</strong><p>{versionEvaluation?.findings ? `${counts("critical")} critical, ${counts("review")} for review.` : "Run the checks from the Safety & Quality page."}</p><small><button className="text-button" onClick={() => setActivePage("Safety & Quality")}>Open full report</button></small></div></div>
          <div className="timeline-item"><span className="timeline-dot gray" /><div><strong>Qualified human review: {item.status.replace("_", " ")}</strong><p>Approval is never inferred from an AI score.</p>
            {reviews.map((review) => <small key={review.id}>{new Date(review.created_at).toLocaleString()} · {review.decision.replace("_", " ")}{review.reviewer ? ` by ${review.reviewer}` : ""}{review.feedback ? ` — ${review.feedback}` : ""}<br /></small>)}
          </div></div>
        </div>

        {item.status === "approved"
          ? <p className="small-note">This version is approved and locked. Regenerate from the original to make further changes.</p>
          : <>
          <label className="field-label" htmlFor="reviewer">Reviewer name</label>
          <input id="reviewer" className="form-input" maxLength={100} value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Qualified reviewer" />
          <label className="field-label" htmlFor="review-feedback">Review comments</label>
          <textarea id="review-feedback" className="form-textarea" maxLength={2000} rows={3} value={reviewFeedback} onChange={(event) => setReviewFeedback(event.target.value)} placeholder="What was checked, and what must change?" />
          <div className="action-row">
            <button className="btn btn-primary" disabled={submittingReview} onClick={() => handleReview("approved")}><CheckCircle2 size={16} /> Approve</button>
            <button className="btn btn-secondary" disabled={submittingReview} onClick={() => handleReview("needs_revision")}><RefreshCw size={16} /> Needs revision</button>
            <button className="btn btn-secondary" disabled={submittingReview} onClick={() => handleReview("rejected")}><X size={16} /> Reject</button>
          </div>
          </>}

        <div className="view-tabs" role="tablist" aria-label="Draft view">
          <button role="tab" aria-selected={view === "diff"} className={view === "diff" ? "active" : ""} onClick={() => setView("diff")}>Compare with original</button>
          <button role="tab" aria-selected={view === "text"} className={view === "text" ? "active" : ""} onClick={() => setView("text")}>Full model output</button>
        </div>
        {/* key remounts the diff per version, so it never shows the previous version's result or error */}
        {view === "diff" ? <DiffView key={item.id} versionId={item.id} /> : <pre className="draft-output">{versionContent || "Loading version content..."}</pre>}
      </section>}
    </>
  );
}

function Intro() {
  return <div className="page-intro"><div><h2>Version history</h2><p>Every generated draft for the selected SOP, with its checks and review decisions.</p></div><Badge tone="blue"><History size={12} /> Version control</Badge></div>;
}
