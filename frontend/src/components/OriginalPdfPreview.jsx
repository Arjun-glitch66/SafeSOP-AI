import { useEffect, useState } from "react";
import { fetchOriginalBlob } from "../api.js";

// The original PDF in the browser's own viewer. The file needs the auth header, so it is
// fetched once and shown from a blob URL; `page` jumps to a page (#page=N).
export default function OriginalPdfPreview({ documentId, page }) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    fetchOriginalBlob(documentId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  if (error) return <p className="small-note">Could not load the original PDF: {error}</p>;
  if (!url) return <p className="small-note">Loading the original PDF…</p>;
  return <iframe key={page} className="pdf-preview" src={`${url}#page=${page || 1}`} title={`Original PDF, page ${page || 1}`} />;
}
