
import { useEffect, useRef, useState } from "react";
import { checkBackend, getDocuments, uploadDocument, createChangeRequest, getChangeRequests } from "./api.js";
import {
  Activity, AlertTriangle, ArrowDownToLine, ArrowLeftRight,
  ArrowUpRight, Bell, BookOpen, Check, CheckCircle2,
  ChevronDown, ChevronLeft, ChevronRight, Clock3, CloudUpload,
  Command, FileCheck2, FileClock, FilePlus2, FileSearch,
  FileText, Files, FlaskConical, FolderOpen, GitCompare,
  History, Home, LayoutDashboard, Menu, MoreHorizontal,
  PanelLeftClose, Plus, RefreshCw, Search, Settings,
  Shield, ShieldAlert, ShieldCheck, Sparkles, Upload,
  Workflow, X, Zap
} from "lucide-react";

const navigation = [
  { label: "Overview", icon: LayoutDashboard, group: "WORKSPACE" },
  { label: "Documents", icon: Files, group: "WORKSPACE" },
  { label: "Revision Studio", icon: GitCompare, group: "WORKSPACE" },
  { label: "Safety & Quality", icon: ShieldCheck, group: "QUALITY" },
  { label: "Version History", icon: History, group: "QUALITY" },
];

const demoVersions = [
  { name: "Machine Maintenance SOP", version: "Rev 03", date: "Oct 19, 2026", status: "In review", initials: "MM" },
  { name: "Equipment Shutdown", version: "Rev 02", date: "Oct 18, 2026", status: "Draft", initials: "ES" },
  { name: "Emergency Response", version: "Rev 01", date: "Oct 16, 2026", status: "Approved", initials: "ER" },
];

const demoFindings = [
  { title: "Required warning preservation", detail: "A source warning needs verification in the revised draft.", severity: "Critical", color: "red" },
  { title: "Step-order integrity", detail: "Confirm isolation occurs before equipment access.", severity: "High", color: "amber" },
  { title: "Unsupported instructions", detail: "Review newly introduced technical values against the source.", severity: "Review", color: "blue" },
];

function Badge({ children, tone = "gray", dot = false }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  );
}

function MetricCard({ label, value, note, icon: Icon, tone = "blue" }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon metric-${tone}`}><Icon size={17} /></span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-note">{note}</div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, text, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={25} /></div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [file, setFile] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [backendOnline, setBackendOnline] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [savingRequest, setSavingRequest] = useState(false);
  const [savedRequests, setSavedRequests] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [scope, setScope] = useState("Full document");
  const [targetPage, setTargetPage] = useState("2");
  const [changeRequest, setChangeRequest] = useState("");
  const [feedback, setFeedback] = useState("");
  const [showRequest, setShowRequest] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedVersion, setSelectedVersion] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);
  const fileInput = useRef(null);

  const isDocumentLoaded = Boolean(file?.id);
  const pageTitle = activePage;

  useEffect(() => {
    async function loadBackendData() {
      try {
        await checkBackend();
        setBackendOnline(true);
        const savedDocuments = await getDocuments();
        setDocuments(savedDocuments);
        if (savedDocuments.length > 0 && !file) {
          // Do not automatically select a document; the user chooses the source.
        }
      } catch {
        setBackendOnline(false);
      }
    }
    loadBackendData();
  }, []);

  async function selectFile(selected) {
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      showNotice("Please choose a PDF file.");
      return;
    }
    if (!backendOnline) {
      showNotice("Backend is offline. Start the FastAPI server and try again.");
      return;
    }

    setUploading(true);
    try {
      const saved = await uploadDocument(selected);
      const savedDocument = {
        id: saved.id,
        name: saved.filename,
        filename: saved.filename,
        sha256: saved.sha256,
        size_bytes: saved.size_bytes,
        created_at: saved.created_at,
      };
      setFile(savedDocument);
      setDocuments((current) => [
        savedDocument,
        ...current.filter((document) => document.id !== saved.id),
      ]);
      setActivePage("Documents");
      showNotice("PDF uploaded and saved to the backend successfully.");
    } catch (error) {
      showNotice(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function showNotice(message) {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 4500);
  }

  async function handleSaveRequest() {
    if (!isDocumentLoaded) {
      showNotice("Upload or select a source PDF first.");
      setActivePage("Documents");
      return;
    }
    if (!changeRequest.trim()) {
      showNotice("Enter the requested process change.");
      return;
    }
    if (!backendOnline) {
      showNotice("Backend is offline. Start the FastAPI server first.");
      return;
    }

    // The current backend supports full-document and page-scoped requests only.
    const requestScope = scope === "Full document" ? "full" : "page";
    const scopedDescription = scope === "Selected page"
      ? `[Target page: ${targetPage}]\\n${changeRequest.trim()}`
      : scope === "Full document"
        ? changeRequest.trim()
        : `[Requested scope: ${scope}. This scope is not yet enforced by the backend.]\\n${changeRequest.trim()}`;

    setSavingRequest(true);
    try {
      const saved = await createChangeRequest(file.id, scopedDescription, requestScope);
      setSavedRequests((current) => [saved, ...current]);
      setShowRequest(true);
      showNotice("Change request saved to the backend. AI generation has not run yet.");
    } catch (error) {
      showNotice(`Could not save request: ${error.message}`);
    } finally {
      setSavingRequest(false);
    }
  }

  const filteredVersions = demoVersions.filter((item) =>
    `${item.name} ${item.version} ${item.status}`
      .toLowerCase().includes(query.toLowerCase())
  );

  function renderOverview() {
    return (
      <>
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow"><Sparkles size={14} /> DOCUMENT INTELLIGENCE PLATFORM</div>
            <h2>Make every revision<br /><span>safer and traceable.</span></h2>
            <p>Revise standard operating procedures with AI-assisted drafting, safety checks, and complete version history.</p>
            <div className="hero-actions">
              <button className="btn btn-primary" onClick={() => { setActivePage("Documents"); setNotice(""); }}>
                <Plus size={17} /> Start a revision
              </button>
              <button className="btn btn-secondary" onClick={() => setActivePage("Safety & Quality")}>
                <ShieldCheck size={17} /> View safety checks
              </button>
            </div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <div className="art-glow" />
            <div className="art-document">
              <div className="art-doc-head"><ShieldCheck size={21} /><span>CONTROLLED DOCUMENT</span><Badge tone="green">REV 03</Badge></div>
              <div className="art-line long" /><div className="art-line medium" />
              <div className="art-section">3. SAFETY PRECAUTIONS</div>
              <div className="art-warning"><AlertTriangle size={15} /><span>Verify all safety requirements</span></div>
              <div className="art-line long" /><div className="art-line short" />
              <div className="art-check"><CheckCircle2 size={16} /><span>Revision tracked</span><CheckCircle2 size={16} /><span>Review required</span></div>
            </div>
            <div className="floating-chip"><span className="chip-check"><Check size={13} /></span> Changes tracked</div>
          </div>
        </section>

        <div className="section-heading">
          <div><h3>Workspace overview</h3><p>Your document activity at a glance.</p></div>
          <span className="muted-label">DEMO DATA</span>
        </div>

        <div className="metrics-grid">
          <MetricCard label="Source documents" value={isDocumentLoaded ? "01" : "00"} note={isDocumentLoaded ? "1 selected in this session" : "No source loaded yet"} icon={Files} />
          <MetricCard label="Generated revisions" value="03" note="Illustrative dashboard data" icon={FileClock} tone="purple" />
          <MetricCard label="Safety checks" value="12" note="Illustrative evaluation data" icon={ShieldCheck} tone="green" />
          <MetricCard label="Needs review" value="02" note="Illustrative open findings" icon={Activity} tone="amber" />
        </div>

        <div className="content-grid overview-grid">
          <section className="panel">
            <div className="panel-heading">
              <div><h3>Recent documents</h3><p>Continue working on an SOP.</p></div>
              <button className="text-button" onClick={() => setActivePage("Documents")}>View library <ChevronRight size={15} /></button>
            </div>
            {isDocumentLoaded && (
              <div className="document-row">
                <div className="file-icon pdf"><FileText size={20} /></div>
                <div className="row-main"><strong>{file.name}</strong><span>Selected locally · Not yet saved to database</span></div>
                <Badge tone="blue">Selected</Badge>
              </div>
            )}
            {demoVersions.slice(0, isDocumentLoaded ? 2 : 3).map((item) => (
              <div className="document-row" key={item.name}>
                <div className="file-icon"><FileText size={20} /></div>
                <div className="row-main"><strong>{item.name}</strong><span>{item.version} · {item.date}</span></div>
                <Badge tone={item.status === "Approved" ? "green" : item.status === "In review" ? "amber" : "gray"}>{item.status}</Badge>
                <button className="icon-button" aria-label="Open version" onClick={() => setActivePage("Version History")}><ChevronRight size={17} /></button>
              </div>
            ))}
            <div className="panel-footnote">Example records are placeholders until connected to SQLite.</div>
          </section>

          <section className="panel">
            <div className="panel-heading"><div><h3>Safety at a glance</h3><p>Review before operational use.</p></div><ShieldAlert size={19} className="subtle-icon" /></div>
            <div className="safety-score">
              <div className="score-ring"><span>—</span><small>NO LIVE<br />SCORE</small></div>
              <div><strong>Evaluation pending</strong><p>Upload a document and run the evaluation pipeline to see real results.</p></div>
            </div>
            <div className="safety-list">
              <div><span className="severity-dot red-dot" /> Warning preservation <span>Not tested</span></div>
              <div><span className="severity-dot amber-dot" /> Step-order integrity <span>Not tested</span></div>
              <div><span className="severity-dot blue-dot" /> Unsupported steps <span>Not tested</span></div>
            </div>
            <button className="btn btn-secondary btn-full" onClick={() => setActivePage("Safety & Quality")}>Open quality center <ArrowUpRight size={16} /></button>
          </section>
        </div>

        <section className="workflow-strip">
          <div className="workflow-title"><Workflow size={18} /><div><strong>Revision workflow</strong><span>From source document to human-reviewed draft</span></div></div>
          {[
            ["01", "Upload source", "Preserve original"],
            ["02", "Describe change", "Specify scope"],
            ["03", "Generate & test", "Evaluate draft"],
            ["04", "Review revision", "Human approval"],
          ].map((step, index) => (
            <button className="workflow-step" key={step[0]} onClick={() => setActivePage(["Documents", "Revision Studio", "Safety & Quality", "Version History"][index])}>
              <span>{step[0]}</span><div><strong>{step[1]}</strong><small>{step[2]}</small></div><ChevronRight size={15} />
            </button>
          ))}
        </section>
      </>
    );
  }

  function renderDocuments() {
    return (
      <>
        <div className="page-intro">
          <div><div className="eyebrow">LIBRARY / DOCUMENTS</div><h2>Document center</h2><p>Upload the controlled source SOP before requesting a revision.</p></div>
          <button className="btn btn-primary" onClick={() => fileInput.current?.click()} disabled={uploading || !backendOnline}><Upload size={16} /> {uploading ? "Uploading..." : "Upload document"}</button>
        </div>

        <div className={`upload-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); }}
          onClick={() => fileInput.current?.click()}
          role="button" tabIndex={0}
          onKeyDown={(event) => { if (event.key === "Enter") fileInput.current?.click(); }}>
          <input ref={fileInput} type="file" accept=".pdf,application/pdf" hidden onChange={(event) => selectFile(event.target.files?.[0])} />
          <div className="upload-icon"><CloudUpload size={27} /></div>
          <h3>{uploading ? "Uploading PDF..." : file ? "Source PDF saved" : "Drop your SOP here"}</h3>
          <p>{file ? file.name : backendOnline ? "Drag and drop a PDF, or click to browse your files." : "Waiting for the Python backend to connect..."}</p>
          <span className="upload-hint">PDF · {backendOnline ? "Backend ready for persistent upload" : "Start the backend at http://127.0.0.1:8000"}</span>
          {file && <Badge tone="green"><Check size={13} /> Saved to backend</Badge>}
        </div>

        <div className="info-cards">
          <div className="info-card"><div className="info-icon purple-bg"><Sparkles size={18} /></div><div><strong>AI-assisted drafting</strong><p>Proposed revisions grounded in the original SOP.</p></div></div>
          <div className="info-card"><div className="info-icon amber-bg"><Zap size={18} /></div><div><strong>Safety-first evaluation</strong><p>Check warnings, instruction support and step order.</p></div></div>
          <div className="info-card"><div className="info-icon green-bg"><ShieldCheck size={18} /></div><div><strong>Version traceability</strong><p>Retain the original and each generated draft.</p></div></div>
        </div>

        <section className="panel">
          <div className="panel-heading"><div><h3>Document library</h3><p>Documents retrieved from the local backend database.</p></div><div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents..." /></div></div>
          {documents.filter((document) => `${document.filename || document.name} ${document.id}`.toLowerCase().includes(query.toLowerCase())).map((document) => <div className="document-row" key={document.id}><div className="file-icon pdf"><FileText size={20} /></div><div className="row-main"><strong>{document.filename || document.name}</strong><span>Saved original · {document.size_bytes ? `${Math.round(document.size_bytes / 1024)} KB` : "PDF"} · {document.created_at ? new Date(document.created_at).toLocaleString() : "Stored"}</span></div><Badge tone="green">Stored</Badge><button className="btn btn-secondary" onClick={() => { setFile({ ...document, name: document.filename || document.name }); setActivePage("Revision Studio"); showNotice("Source document selected for the revision workspace."); }}>Use source</button></div>)}
          {documents.length === 0 && <EmptyState icon={FolderOpen} title="No saved documents yet" text={backendOnline ? "Upload a PDF above to add the first source SOP." : "Start the Python backend to load your saved documents."} />}
          {file && <div className="panel-footnote">Selected source: {file.name} · Original stored separately and not overwritten.</div>}
        </section>
      </>
    );
  }

  function renderRevision() {
    return (
      <>
        <div className="page-intro"><div><div className="eyebrow">WORKSPACE / REVISION STUDIO</div><h2>Revision studio</h2><p>Define the change and choose exactly what you want generated.</p></div><Badge tone="amber" dot>Draft workspace</Badge></div>

        <div className="content-grid revision-grid">
          <section className="panel">
            <div className="panel-heading"><div><h3>Change request</h3><p>Describe the engineer-approved process change.</p></div><FilePlus2 size={19} className="subtle-icon" /></div>
            <label className="field-label">Source document</label>
            <div className="source-select"><FileText size={18} /><div><strong>{file ? file.name : "No source selected"}</strong><span>{file ? "Original stored in backend" : "Upload or choose a saved PDF in Document Center first"}</span></div><button className="text-button" onClick={() => setActivePage("Documents")}>Choose</button></div>

            <label className="field-label">Output scope</label>
            <div className="scope-options">
              {[
                { name: "Full document", desc: "Complete revised SOP", icon: Files },
                { name: "Selected page", desc: "One page only", icon: FileText },
                { name: "Selected section", desc: "Named section", icon: BookOpen },
                { name: "Selected step", desc: "Specific procedure step", icon: Workflow },
              ].map((item) => <button key={item.name} className={`scope-option ${scope === item.name ? "selected" : ""}`} onClick={() => setScope(item.name)}><item.icon size={19} /><span><strong>{item.name}</strong><small>{item.desc}</small></span>{scope === item.name && <CheckCircle2 size={16} className="scope-check" />}</button>)}
            </div>

            {scope === "Selected page" && <><label className="field-label">Target page</label><input className="form-input" type="number" min="1" value={targetPage} onChange={(event) => setTargetPage(event.target.value)} /></>}

            <label className="field-label">Requested change <span className="required">*</span></label>
            <textarea className="form-textarea" value={changeRequest} onChange={(event) => setChangeRequest(event.target.value)} placeholder="Describe what changed, why it changed, and which safety requirements must remain unchanged..." rows={6} />

            <div className="form-note"><ShieldCheck size={16} /><span>Safety warnings and critical prerequisites must be preserved or explicitly flagged for qualified review.</span></div>
            <button className="btn btn-primary btn-full" disabled={savingRequest || !backendOnline} onClick={handleSaveRequest}><Check size={16} /> {savingRequest ? "Saving request..." : "Save change request"}</button>
          </section>

          <div className="stack">
            <section className="panel">
              <div className="panel-heading"><div><h3>Request progress</h3><p>Preparation checklist</p></div><Activity size={18} className="subtle-icon" /></div>
              <div className="progress-count">{showRequest ? "2" : file ? "1" : "0"}<span> / 4 steps</span></div>
              <div className="progress-track"><span style={{ width: `${showRequest ? 50 : file ? 25 : 0}%` }} /></div>
              {["Source document selected", "Change request described", "Draft generated and evaluated", "Qualified human review"].map((label, index) => <div className="checklist-row" key={label}><span className={`check-circle ${index === 0 && file || index === 1 && showRequest ? "complete" : ""}`}>{index === 0 && file || index === 1 && showRequest ? <Check size={12} /> : index + 1}</span><span>{label}</span></div>)}
            </section>
            <section className="panel">
              <div className="panel-heading"><div><h3>Generation settings</h3><p>Intended pipeline configuration</p></div><Settings size={18} className="subtle-icon" /></div>
              <div className="setting-row"><span>Original as source of truth</span><Badge tone="green">Required</Badge></div>
              <div className="setting-row"><span>Retain earlier versions</span><Badge tone="green">Enabled</Badge></div>
              <div className="setting-row"><span>Automatic safety approval</span><Badge tone="red">Disabled</Badge></div>
              <p className="small-note">The API currently saves requests only. AI drafting, page extraction and real safety evaluation are not connected yet.</p>
            </section>
          </div>
        </div>

        {showRequest && <section className="panel request-summary"><div className="panel-heading"><div><h3>Saved request preview</h3><p>Saved change request. AI generation has not run yet.</p></div><Badge tone="blue">Prepared</Badge></div><p><strong>Scope:</strong> {scope}</p><p><strong>Change:</strong> {changeRequest}</p>{savedRequests[0] && <p><strong>Request ID:</strong> {savedRequests[0].id}</p>}<button className="btn btn-primary" onClick={() => showNotice("AI generation is the next integration step; this request is saved.")}><Sparkles size={16} /> Continue to generation (coming next)</button></section>}
      </>
    );
  }

  function renderSafety() {
    return (
      <>
        <div className="page-intro"><div><div className="eyebrow">QUALITY / SAFETY EVALUATION</div><h2>Safety & quality center</h2><p>Review safety-critical generated text against the immutable source.</p></div><Badge tone="amber" dot>Human review required</Badge></div>
        <div className="notice-banner"><ShieldAlert size={20} /><div><strong>No live evaluation results yet</strong><p>The findings below are illustrative examples. Real scores will appear only after the Python evaluator is connected and run on an actual document.</p></div></div>
        <div className="metrics-grid">
          <MetricCard label="Warning recall" value="—" note="Requires source labels" icon={AlertTriangle} tone="amber" />
          <MetricCard label="Unsupported instructions" value="—" note="Requires evidence checks" icon={FileSearch} tone="red" />
          <MetricCard label="Step-order integrity" value="—" note="Requires critical dependencies" icon={Workflow} tone="purple" />
          <MetricCard label="Evaluation status" value="Pending" note="No verified run yet" icon={FlaskConical} tone="blue" />
        </div>
        <section className="panel">
          <div className="panel-heading"><div><h3>Evaluation framework</h3><p>Safety-critical checks required by the capstone.</p></div><Badge tone="blue">Framework preview</Badge></div>
          {[
            ["01", "Warning preservation", "Compare every source-required warning with the revised draft; investigate omissions and altered severity.", "Critical"],
            ["02", "Hallucination and unsupported steps", "Check generated instructions against source content and explicit engineer-provided change data.", "Critical"],
            ["03", "Critical step ordering", "Verify required prerequisite relationships and flag missing or reversed dependencies.", "Critical"],
            ["04", "Unintended changes", "Identify changes outside the requested scope and verify that unaffected content remains intact.", "High"],
          ].map((item) => <div className="framework-row" key={item[0]}><span className="framework-number">{item[0]}</span><div className="row-main"><strong>{item[1]}</strong><span>{item[2]}</span></div><Badge tone="red">{item[3]}</Badge></div>)}
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h3>Findings preview</h3><p>Example finding types, not actual test results.</p></div><button className="text-button" onClick={() => showNotice("Real findings will be loaded from SQLite after API integration.")}>Details <ChevronRight size={15} /></button></div>
          {demoFindings.map((item) => <div className="finding-row" key={item.title}><div className={`finding-icon finding-${item.color}`}><AlertTriangle size={18} /></div><div className="row-main"><strong>{item.title}</strong><span>{item.detail}</span></div><Badge tone={item.color}>{item.severity}</Badge></div>)}
        </section>
      </>
    );
  }

  function renderHistory() {
    const item = demoVersions[selectedVersion];
    return (
      <>
        <div className="page-intro"><div><div className="eyebrow">QUALITY / DOCUMENT CONTROL</div><h2>Version history</h2><p>Keep the original immutable and trace every generated revision.</p></div><Badge tone="blue"><History size={12} /> Version control</Badge></div>
        <div className="notice-banner"><History size={20} /><div><strong>Persistent version history is not connected yet</strong><p>The entries below are illustrative records. Generated versions and evaluation results will come from SQLite after backend integration.</p></div></div>
        <section className="panel">
          <div className="panel-heading"><div><h3>Revision register</h3><p>Example document records</p></div><div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search versions..." /></div></div>
          <div className="table-wrap"><table className="data-table"><thead><tr><th>DOCUMENT</th><th>REVISION</th><th>LAST UPDATED</th><th>STATUS</th><th></th></tr></thead><tbody>{filteredVersions.map((version) => { const index = demoVersions.indexOf(version); return <tr key={version.name} className={selectedVersion === index ? "selected-row" : ""} onClick={() => setSelectedVersion(index)}><td><div className="table-doc"><span className="file-icon"><FileText size={18} /></span><span><strong>{version.name}</strong><small>{version.initials} · SOP document</small></span></div></td><td>{version.version}</td><td>{version.date}</td><td><Badge tone={version.status === "Approved" ? "green" : version.status === "In review" ? "amber" : "gray"} dot>{version.status}</Badge></td><td><button className="icon-button" onClick={(event) => { event.stopPropagation(); setSelectedVersion(index); }}><ChevronRight size={16} /></button></td></tr>; })}</tbody></table></div>
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h3>Revision timeline</h3><p>{item.name}</p></div><Badge tone="gray">{item.version}</Badge></div>
          <div className="timeline">
            <div className="timeline-item"><span className="timeline-dot blue" /><div><strong>{item.version} · Draft created</strong><p>Generated content will be linked to the original source and request.</p><small>{item.date}</small></div></div>
            <div className="timeline-item"><span className="timeline-dot amber" /><div><strong>Safety evaluation</strong><p>Warnings, unsupported instructions and step ordering must be evaluated.</p><small>Pending real backend result</small></div></div>
            <div className="timeline-item"><span className="timeline-dot gray" /><div><strong>Qualified human review</strong><p>Review, reject or request a new revision. Approval is never inferred from an AI score.</p><small>Awaiting reviewer</small></div></div>
          </div>
        </section>
      </>
    );
  }

  const renderers = {
    Overview: renderOverview,
    Documents: renderDocuments,
    "Revision Studio": renderRevision,
    "Safety & Quality": renderSafety,
    "Version History": renderHistory,
  };

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {mobileNav && <button className="mobile-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div className="brand-text">SafeSOP<span>AI</span><small>DOCUMENT INTELLIGENCE</small></div>
          <button className="icon-button sidebar-collapse" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar"><PanelLeftClose size={17} /></button>
        </div>
        <button className={`workspace-select ${activePage === "Overview" ? "workspace-active" : ""}`} onClick={() => { setActivePage("Overview"); setMobileNav(false); }}>
          <span className="workspace-avatar"><LayoutDashboard size={17} /></span>
          <span><strong>My workspace</strong><small>Personal environment</small></span><ChevronDown size={15} />
        </button>
        {["WORKSPACE", "QUALITY"].map((group) => <div className="nav-group" key={group}><div className="nav-label">{group}</div>{navigation.filter((item) => item.group === group).map((item) => <button key={item.label} className={`nav-item ${activePage === item.label ? "nav-active" : ""}`} onClick={() => { setActivePage(item.label); setMobileNav(false); }}><item.icon size={18} /><span>{item.label}</span>{item.label === "Safety & Quality" && <span className="nav-count">!</span>}</button>)}</div>)}
        <div className="sidebar-bottom"><div className="storage-card"><div className="storage-icon"><Shield size={17} /></div><strong>Controlled documents</strong><p>Originals and revisions must remain traceable.</p><div className="storage-track"><span /></div><small>Local prototype · Not cloud storage</small></div><button className="nav-item" onClick={() => showNotice("Settings will be implemented with the backend.")}><Settings size={18} /><span>Settings</span></button><div className="profile-row"><div className="profile-avatar">AU</div><div><strong>Project workspace</strong><small>Local development</small></div><MoreHorizontal size={18} /></div></div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14} /><strong>{pageTitle}</strong></div></div>
          <div className="topbar-right"><div className="global-search"><Search size={16} /><input placeholder="Search workspace..." value={query} onChange={(event) => setQuery(event.target.value)} /><kbd><Command size={11} /> K</kbd></div><button className="icon-button notification-button" onClick={() => showNotice("No notifications yet.")} aria-label="Notifications"><Bell size={19} /><span /></button><div className="top-profile"><div className="profile-avatar">AU</div><ChevronDown size={14} /></div></div>
        </header>

        <div className="page-content">
          <div className="mobile-title"><span className="eyebrow">SAFESOP AI WORKSPACE</span><h1>{pageTitle}</h1></div>
          {renderers[activePage]()}
          <footer className="app-footer"><span><ShieldCheck size={14} /> SafeSOP AI <span className="footer-separator">·</span> AI-assisted drafting</span><span>Prototype UI <span className="footer-separator">·</span> Human review required</span></footer>
        </div>
      </main>
      {notice && <div className="toast"><div className="toast-icon"><CheckCircle2 size={17} /></div><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss notification"><X size={15} /></button></div>}
    </div>
  );
}
