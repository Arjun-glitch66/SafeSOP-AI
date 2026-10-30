import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { CloudUpload, FileText, FolderOpen, Search, Upload } from "lucide-react";
import { getDocuments, uploadDocument } from "../api.js";
import { EmptyState } from "../components/ui.jsx";
import { useAuth, useBackend, useNotice, useResource, useTitle } from "../state.jsx";

export default function DocumentsPage() {
  useTitle("Documents");
  const { online } = useBackend();
  const { can } = useAuth();
  const { show } = useNotice();
  const navigate = useNavigate();
  const documents = useResource(getDocuments, [online]);
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef(null);
  const canUpload = can("author") && online && !uploading;

  async function handleFile(selected) {
    if (fileInput.current) fileInput.current.value = "";
    if (!selected || !canUpload) return;
    if (!selected.name.toLowerCase().endsWith(".pdf")) {
      show("Please choose a PDF file.", "error");
      return;
    }
    setUploading(true);
    try {
      const saved = await uploadDocument(selected);
      show("PDF uploaded. The original is stored unchanged.");
      navigate(`/documents/${saved.id}`);
    } catch (error) {
      show(`Upload failed: ${error.message}`, "error");
    } finally {
      setUploading(false);
    }
  }

  const visible = (documents.data || []).filter((document) =>
    `${document.filename} ${document.id}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <div className="page-intro">
        <div><h1>Documents</h1><p>Upload the source SOP first. The original PDF is stored as-is and never overwritten.</p></div>
        {can("author") && <button className="btn btn-primary" onClick={() => fileInput.current?.click()} disabled={!canUpload}><Upload size={16} /> {uploading ? "Uploading..." : "Upload document"}</button>}
      </div>

      {can("author") && <div className={`upload-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); handleFile(event.dataTransfer.files[0]); }}
        onClick={() => fileInput.current?.click()}
        role="button" tabIndex={0} aria-label="Upload a source PDF"
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.current?.click(); } }}>
        <input ref={fileInput} type="file" accept=".pdf,application/pdf" hidden onChange={(event) => handleFile(event.target.files?.[0])} />
        <div className="upload-icon"><CloudUpload size={32} /></div>
        <h2>{uploading ? "Uploading PDF..." : "Drop your SOP here"}</h2>
        <p>{online ? "Drag and drop a PDF, or click to browse your files." : "Waiting for the backend server to connect..."}</p>
        <span className="upload-hint">PDF with selectable text · up to 20 MB{online ? "" : " · start the backend server"}</span>
      </div>}

      <section className="panel">
        <div className="panel-heading"><div><h2>Document library</h2><p>Choose a document to revise or review.</p></div><div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents..." aria-label="Search documents" /></div></div>
        {documents.error && <p className="form-error" role="alert">Could not load documents: {documents.error.message}</p>}
        {visible.map((document) => (
          <div className="document-row" key={document.id}>
            <div className="file-icon pdf"><FileText size={20} /></div>
            <div className="row-main"><strong>{document.filename}</strong><span>Original, {document.size_bytes ? `${Math.round(document.size_bytes / 1024)} KB` : "PDF"} · {document.version_count || 0} draft{document.version_count === 1 ? "" : "s"} · {new Date(document.created_at).toLocaleString()}</span></div>
            <Link className="btn btn-secondary" to={`/documents/${document.id}`}>Open</Link>
          </div>
        ))}
        {!documents.loading && !documents.error && visible.length === 0 && <EmptyState icon={FolderOpen} title={query ? "No matching documents" : "No saved documents yet"} text={can("author") ? "Upload a PDF above to add the first source SOP." : "An author has not uploaded any SOPs yet."} />}
      </section>
    </>
  );
}
