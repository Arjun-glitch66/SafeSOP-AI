import { ArrowUpRight, ChevronRight, FileText, History, Plus, ShieldAlert, Upload } from "lucide-react";
import { Badge } from "../components/ui.jsx";
import { evaluationLabel, percent, statusLabel } from "../components/labels.js";

export default function Overview({ app }) {
  const { documents, file, setFile, setActivePage, totalVersions, versions, pageCount, versionEvaluation, selectedVersion } = app;
  const metrics = versionEvaluation?.metrics;
  const latest = versions[0];  // versions arrive newest first
  const awaiting = versions.filter((version) => version.status !== "approved" && version.status !== "rejected").length;

  return (
    <>
      {/* Title block of the selected SOP, the way a controlled drawing or document is identified. */}
      <section className="title-block" aria-label="Selected document">
        <div className="title-block-head">
          <div>
            <p className="title-block-kicker">{file ? "Selected source document" : "Get started"}</p>
            <h1>{file ? file.name.replace(/\.pdf$/i, "").replaceAll("_", " ") : "No SOP selected"}</h1>
            <p>{file
              ? "Every draft is generated from this original PDF and needs a qualified reviewer's sign-off before use."
              : "Upload an SOP PDF and describe the process change. SafeSOP drafts the revision, checks it against the original, and keeps every version for review."}</p>
          </div>
          <div className="action-row">
            {file ? <>
              <button className="btn btn-primary" onClick={() => setActivePage("Revision Studio")}><Plus size={16} /> New revision</button>
              <button className="btn btn-secondary" onClick={() => setActivePage("Version History")}><History size={16} /> Review versions</button>
            </> : <button className="btn btn-primary" onClick={() => setActivePage("Documents")}><Upload size={16} /> Upload an SOP</button>}
          </div>
        </div>
        <dl className="title-block-fields">
          <div><dt>Latest revision</dt><dd>{latest ? `v${latest.version_number}` : "None"}</dd></div>
          <div><dt>Automated check</dt><dd>{latest?.evaluation_status ? evaluationLabel[latest.evaluation_status] : "Not run"}</dd></div>
          <div><dt>Review status</dt><dd>{statusLabel(latest?.status)}</dd></div>
          <div><dt>Awaiting review</dt><dd>{file ? awaiting : "None"}</dd></div>
          <div><dt>Pages</dt><dd>{pageCount ?? "Unknown"}</dd></div>
        </dl>
      </section>

      <div className="content-grid overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div><h3>Recent documents</h3><p>{documents.length} stored, {totalVersions} drafts generated</p></div>
            <button className="text-button" onClick={() => setActivePage("Documents")}>View library <ChevronRight size={15} /></button>
          </div>
          {documents.slice(0, 4).map((document) => (
            <div className="document-row" key={document.id}>
              <div className="file-icon pdf"><FileText size={20} /></div>
              <div className="row-main"><strong>{document.filename}</strong><span>{document.version_count || 0} draft{document.version_count === 1 ? "" : "s"}, uploaded {document.created_at ? new Date(document.created_at).toLocaleDateString() : "earlier"}</span></div>
              {file?.id === document.id && <Badge tone="blue">Selected</Badge>}
              <button className="icon-button" aria-label={`Open version history for ${document.filename}`} onClick={() => { setFile({ ...document, name: document.filename }); setActivePage("Version History"); }}><ChevronRight size={17} /></button>
            </div>
          ))}
          {documents.length === 0 && <div className="panel-footnote">No documents yet. Upload a source PDF to begin.</div>}
        </section>

        <section className="panel">
          <div className="panel-heading"><div><h3>Safety at a glance</h3><p>Automated checks for the open version</p></div><ShieldAlert size={19} className="subtle-icon" /></div>
          <div className="safety-score">
            <div className="score-ring"><span>{metrics ? percent(metrics.warning_recall) : "–"}</span><small>warnings kept</small></div>
            <div><strong>{versionEvaluation ? `Version ${selectedVersion?.version_number ?? ""}: ${evaluationLabel[versionEvaluation.status]}` : "No version open"}</strong><p>{versionEvaluation ? "Automated checks only. A qualified reviewer must still approve it." : "Generate a draft or open a version to see its checks."}</p></div>
          </div>
          <div className="safety-list">
            <div><span className="severity-dot red-dot" /> Warnings preserved <span>{metrics ? percent(metrics.warning_recall) : "Not checked"}</span></div>
            <div><span className="severity-dot amber-dot" /> Step order kept <span>{metrics ? percent(metrics.order_integrity) : "Not checked"}</span></div>
            <div><span className="severity-dot blue-dot" /> Unsupported steps <span>{metrics ? percent(metrics.unsupported_instruction_rate) : "Not checked"}</span></div>
          </div>
          <button className="btn btn-secondary btn-full" onClick={() => setActivePage("Safety & Quality")}>Open safety report <ArrowUpRight size={16} /></button>
        </section>
      </div>

      <nav className="workflow-strip" aria-label="Revision workflow">
        {[
          ["1", "Upload source", "The original is kept unchanged", "Documents"],
          ["2", "Describe change", "Full document or one page", "Revision Studio"],
          ["3", "Check draft", "Automated safety checks", "Safety & Quality"],
          ["4", "Review", "A person approves or rejects", "Version History"],
        ].map(([number, title, subtitle, page]) => (
          <button className="workflow-step" key={number} onClick={() => setActivePage(page)}>
            <span>{number}</span><div><strong>{title}</strong><small>{subtitle}</small></div><ChevronRight size={15} />
          </button>
        ))}
      </nav>
    </>
  );
}
