import { useEffect, useRef, useState } from "react";
import {
  checkBackend, getDocuments, getDocument, uploadDocument, createChangeRequest,
  generateRevision, getDocumentVersions, getVersionContent, getEvaluations,
  runEvaluation, getReviews, createReview, getEvaluationStatus,
} from "./api.js";
import {
  AlertTriangle, CheckCircle2, ChevronRight, FileText, Files, GitCompare, History, LayoutDashboard, Menu,
  PanelLeftClose, Shield, ShieldCheck, X,
} from "lucide-react";
import { evaluationLabel } from "./components/labels.js";
import Overview from "./pages/Overview.jsx";
import Documents from "./pages/Documents.jsx";
import RevisionStudio from "./pages/RevisionStudio.jsx";
import SafetyQuality from "./pages/SafetyQuality.jsx";
import VersionHistory from "./pages/VersionHistory.jsx";

const navigation = [
  { label: "Overview", icon: LayoutDashboard, group: "Workspace", page: Overview },
  { label: "Documents", icon: Files, group: "Workspace", page: Documents },
  { label: "Revision Studio", icon: GitCompare, group: "Workspace", page: RevisionStudio },
  { label: "Safety & Quality", icon: ShieldCheck, group: "Quality", page: SafetyQuality },
  { label: "Version History", icon: History, group: "Quality", page: VersionHistory },
];

// All shared state lives here; each page receives it as one `app` object.
export default function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [evaluatorVersion, setEvaluatorVersion] = useState("");

  const [documents, setDocuments] = useState([]);
  const [file, setFile] = useState(null);
  const [pageCount, setPageCount] = useState(null);
  const [uploading, setUploading] = useState(false);

  const [scope, setScope] = useState("Full document");
  const [targetPage, setTargetPage] = useState("1");
  const [changeRequest, setChangeRequest] = useState("");
  const [parentVersion, setParentVersion] = useState(null);
  const [savingRequest, setSavingRequest] = useState(false);
  const [savedRequests, setSavedRequests] = useState([]);
  const [showRequest, setShowRequest] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(null);

  const [versions, setVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [versionContent, setVersionContent] = useState("");
  const [versionEvaluation, setVersionEvaluation] = useState(null);
  const [evaluating, setEvaluating] = useState(false);
  const [reviews, setReviews] = useState([]);
  const [reviewer, setReviewer] = useState("");
  const [reviewFeedback, setReviewFeedback] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

  // The most recently requested document / version. Responses for anything older are
  // ignored, so a slow reply can never fill the screen with another item's data.
  const currentDocumentId = useRef(null);
  const currentVersionId = useRef(null);

  const selectedVersion = versions.find((version) => version.id === selectedVersionId);
  const totalVersions = documents.reduce((sum, document) => sum + (document.version_count || 0), 0);

  function showNotice(message, tone = "success") {
    setNotice({ message, tone });
    window.setTimeout(() => setNotice(null), 6000);
  }

  async function refreshVersions(documentId) {
    try {
      const loaded = await getDocumentVersions(documentId);
      if (currentDocumentId.current === documentId) setVersions(loaded);
    } catch (error) {
      if (currentDocumentId.current !== documentId) return;
      setVersions([]);
      showNotice(`Could not load versions: ${error.message}`, "error");
    }
  }

  useEffect(() => {
    async function loadBackendData() {
      try {
        await checkBackend();
        setBackendOnline(true);
        setDocuments(await getDocuments());
        setEvaluatorVersion((await getEvaluationStatus()).evaluator_version);
      } catch {
        setBackendOnline(false);
      }
    }
    loadBackendData();
  }, []);

  // Switching source document resets everything that belongs to the previous one.
  useEffect(() => {
    setVersions([]);
    setSelectedVersionId(null);
    setVersionContent("");
    setGenerated(null);
    setVersionEvaluation(null);
    setReviews([]);
    setParentVersion(null);
    setPageCount(null);
    currentDocumentId.current = file?.id ?? null;
    currentVersionId.current = null;
    if (!file?.id) return;
    const documentId = file.id;
    refreshVersions(documentId);
    getDocument(documentId)
      .then((details) => { if (currentDocumentId.current === documentId) setPageCount(details.page_count); })
      .catch(() => {});
  }, [file?.id]);

  async function uploadFile(selected) {
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      showNotice("Please choose a PDF file.", "error");
      return;
    }
    if (!backendOnline) {
      showNotice("Backend is offline. Start the FastAPI server and try again.", "error");
      return;
    }
    setUploading(true);
    try {
      const saved = await uploadDocument(selected);
      const savedDocument = { ...saved, name: saved.filename, version_count: 0 };
      setFile(savedDocument);
      setDocuments((current) => [savedDocument, ...current.filter((document) => document.id !== saved.id)]);
      showNotice("PDF uploaded and saved to the backend successfully.");
    } catch (error) {
      showNotice(`Upload failed: ${error.message}`, "error");
    } finally {
      setUploading(false);
    }
  }

  function chooseSource(document) {
    setFile({ ...document, name: document.filename });
    setActivePage("Revision Studio");
    showNotice("Source document selected for the revision workspace.");
  }

  function requestIsReady() {
    if (!file?.id) {
      showNotice("Upload or select a source PDF first.", "error");
      setActivePage("Documents");
      return false;
    }
    if (!changeRequest.trim()) {
      showNotice("Enter the requested process change.", "error");
      return false;
    }
    if (!backendOnline) {
      showNotice("Backend is offline. Start the FastAPI server first.", "error");
      return false;
    }
    const page = Number(targetPage);
    if (scope === "Selected page" && (!(page >= 1) || (pageCount && page > pageCount))) {
      showNotice(`Enter a target page between 1 and ${pageCount || "the last page"}.`, "error");
      return false;
    }
    return true;
  }

  // The backend supports full-document and page-scoped requests only.
  const requestScope = scope === "Full document" ? "full" : "page";

  // requestId: generate from that saved change request instead of the form fields.
  async function handleGenerate(requestId = null) {
    if (!requestId && !requestIsReady()) return;
    setGenerating(true);
    setGenerated(null);
    try {
      // The backend always reads the immutable original PDF, never a previous draft.
      const result = await generateRevision(file.id, changeRequest.trim(), requestScope, Number(targetPage), parentVersion?.id, requestId);
      setGenerated(result);
      setParentVersion(null);
      currentVersionId.current = result.version_id;
      setSelectedVersionId(result.version_id);
      setVersionContent(result.content);
      setVersionEvaluation(result.safety_evaluation);
      setReviews([]);
      await refreshVersions(file.id);
      setDocuments(await getDocuments());
      showNotice(`Draft saved as version ${result.version_number}. Automated check: ${evaluationLabel[result.safety_evaluation?.status] || "not run"}.`);
    } catch (error) {
      showNotice(`Generation failed: ${error.message}`, "error");
    } finally {
      setGenerating(false);
    }
  }

  async function handleSaveRequest() {
    if (!requestIsReady()) return;
    setSavingRequest(true);
    try {
      const saved = await createChangeRequest(file.id, changeRequest.trim(), requestScope, Number(targetPage));
      setSavedRequests((current) => [saved, ...current]);
      setShowRequest(true);
      showNotice("Change request saved to the backend. AI generation has not run yet.");
    } catch (error) {
      showNotice(`Could not save request: ${error.message}`, "error");
    } finally {
      setSavingRequest(false);
    }
  }

  async function openVersion(versionId) {
    currentVersionId.current = versionId;
    setSelectedVersionId(versionId);
    setVersionContent("");
    setVersionEvaluation(null);
    setReviews([]);
    try {
      const [content, evaluations, savedReviews] = await Promise.all([
        getVersionContent(versionId), getEvaluations(versionId), getReviews(versionId),
      ]);
      if (currentVersionId.current !== versionId) return;  // user already opened another version
      setVersionContent(content);
      setVersionEvaluation(evaluations[0] || null);
      setReviews(savedReviews);
    } catch (error) {
      showNotice(`Could not load version: ${error.message}`, "error");
    }
  }

  async function handleRunEvaluation() {
    setEvaluating(true);
    try {
      const versionId = selectedVersionId;
      const result = await runEvaluation(versionId);
      if (currentVersionId.current !== versionId) return;
      setVersionEvaluation(result);
      await refreshVersions(file.id);
      // The API answers 200 with status "error" when the evaluator itself crashed.
      showNotice(result.status === "error" ? result.message : "Automated checks re-run and saved.", result.status === "error" ? "error" : "success");
    } catch (error) {
      showNotice(`Evaluation failed: ${error.message}`, "error");
    } finally {
      setEvaluating(false);
    }
  }

  async function handleReview(decision) {
    if (decision === "approved" && versionEvaluation?.status !== "pass_automated") {
      if (!reviewFeedback.trim()) {
        showNotice("Automated checks did not pass. Explain in the review comments why you are approving anyway.", "error");
        return;
      }
      if (!window.confirm("Automated checks did not pass for this version. Approve it anyway as the qualified reviewer?")) return;
    }
    setSubmittingReview(true);
    try {
      const review = await createReview(selectedVersionId, decision, reviewer, reviewFeedback);
      setReviews((current) => [review, ...current]);
      setReviewFeedback("");
      await refreshVersions(file.id);
      showNotice(`Review saved: ${decision.replace("_", " ")}.`);
    } catch (error) {
      showNotice(`Could not save review: ${error.message}`, "error");
    } finally {
      setSubmittingReview(false);
    }
  }

  function startRegeneration(version) {
    setParentVersion(version);
    setChangeRequest(version.change_request || "");
    setScope(version.scope === "page" ? "Selected page" : "Full document");
    if (version.target_page) setTargetPage(String(version.target_page));
    setGenerated(null);
    setActivePage("Revision Studio");
  }

  const app = {
    setActivePage, query, setQuery, backendOnline, evaluatorVersion,
    documents, file, setFile, pageCount, uploading, uploadFile, chooseSource, totalVersions,
    scope, setScope, targetPage, setTargetPage, changeRequest, setChangeRequest,
    parentVersion, setParentVersion, savingRequest, savedRequests, showRequest,
    generating, generated, handleGenerate, handleSaveRequest,
    versions, selectedVersion, openVersion, versionContent, versionEvaluation, evaluating,
    handleRunEvaluation, reviews, reviewer, setReviewer, reviewFeedback, setReviewFeedback,
    submittingReview, handleReview, startRegeneration,
  };
  const Page = navigation.find((item) => item.label === activePage).page;

  function navigate(label) {
    setActivePage(label);
    setQuery("");
    setMobileNav(false);
  }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {mobileNav && <button className="mobile-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={22} /></div>
          <div className="brand-text">SafeSOP<span>AI</span><small>Controlled SOP revision</small></div>
          <button className="icon-button sidebar-collapse" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar"><PanelLeftClose size={17} /></button>
        </div>
        <nav aria-label="Main">
          {["Workspace", "Quality"].map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-label">{group}</div>
              {navigation.filter((item) => item.group === group).map((item) => (
                <button key={item.label} className={`nav-item ${activePage === item.label ? "nav-active" : ""}`} aria-current={activePage === item.label ? "page" : undefined} onClick={() => navigate(item.label)}>
                  <item.icon size={18} /><span>{item.label}</span>
                  {item.label === "Safety & Quality" && versionEvaluation?.status === "fail" && <span className="nav-count" aria-label="Selected version failed automated checks">!</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className={`storage-card ${backendOnline ? "online" : "offline"}`}><div className="storage-icon"><Shield size={17} /></div><strong>Originals never change</strong><p>Every draft is traced back to the PDF it came from.</p><small>{backendOnline ? "Backend connected" : "Backend offline"}</small></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-button mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14} /><strong>{activePage}</strong></div></div>
          <div className="topbar-right">{file && <button className="topbar-source" title="Change source document" onClick={() => navigate("Documents")}><FileText size={15} /><span>{file.name}</span></button>}</div>
        </header>

        <div className="page-content">
          <Page app={app} />
          <footer className="app-footer"><span><ShieldCheck size={14} /> SafeSOP AI prototype</span><span>AI drafts are never safety-approved without a qualified reviewer.</span></footer>
        </div>
      </main>
      {notice && <div className={`toast ${notice.tone === "error" ? "toast-error" : ""}`} role={notice.tone === "error" ? "alert" : "status"}><div className="toast-icon">{notice.tone === "error" ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}</div><span>{notice.message}</span><button onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={15} /></button></div>}
    </div>
  );
}
