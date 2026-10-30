import { useRef, useState } from "react";
import { Check, CloudUpload, FileText, FolderOpen, Search, Upload } from "lucide-react";
import { Badge, EmptyState } from "../components/ui.jsx";

export default function Documents({ app }) {
  const { documents, file, backendOnline, uploading, uploadFile, chooseSource, query, setQuery } = app;
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  async function handleFile(selected) {
    await uploadFile(selected);
    if (fileInput.current) fileInput.current.value = "";
  }

  const visible = documents.filter((document) =>
    `${document.filename} ${document.id}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <div className="page-intro">
        <div><h1>Documents</h1><p>Upload the source SOP first. The original PDF is stored as-is and never overwritten.</p></div>
        <button className="btn btn-primary" onClick={() => fileInput.current?.click()} disabled={uploading || !backendOnline}><Upload size={16} /> {uploading ? "Uploading..." : "Upload document"}</button>
      </div>

      <div className={`upload-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); handleFile(event.dataTransfer.files[0]); }}
        onClick={() => fileInput.current?.click()}
        role="button" tabIndex={0} aria-label="Upload a source PDF"
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.current?.click(); } }}>
        <input ref={fileInput} type="file" accept=".pdf,application/pdf" hidden onChange={(event) => handleFile(event.target.files?.[0])} />
        <div className="upload-icon"><CloudUpload size={32} /></div>
        <h3>{uploading ? "Uploading PDF..." : file ? "Source PDF saved" : "Drop your SOP here"}</h3>
        <p>{file ? file.name : backendOnline ? "Drag and drop a PDF, or click to browse your files." : "Waiting for the Python backend to connect..."}</p>
        <span className="upload-hint">PDF with selectable text · up to 20 MB{backendOnline ? "" : " · start the backend server"}</span>
        {file && <Badge tone="green"><Check size={13} /> Saved to backend</Badge>}
      </div>


      <section className="panel">
        <div className="panel-heading"><div><h3>Document library</h3><p>Choose a document to revise.</p></div><div className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents..." aria-label="Search documents" /></div></div>
        {visible.map((document) => (
          <div className="document-row" key={document.id}>
            <div className="file-icon pdf"><FileText size={20} /></div>
            <div className="row-main"><strong>{document.filename}</strong><span>Original, {document.size_bytes ? `${Math.round(document.size_bytes / 1024)} KB` : "PDF"} · {document.created_at ? new Date(document.created_at).toLocaleString() : "Stored"}</span></div>
                        <button className="btn btn-secondary" onClick={() => chooseSource(document)}>Revise this SOP</button>
          </div>
        ))}
        {documents.length === 0 && <EmptyState icon={FolderOpen} title="No saved documents yet" text={backendOnline ? "Upload a PDF above to add the first source SOP." : "Start the Python backend to load your saved documents."} />}
        {file && <div className="panel-footnote">Selected source: {file.name} · Original stored separately and not overwritten.</div>}
      </section>
    </>
  );
}
