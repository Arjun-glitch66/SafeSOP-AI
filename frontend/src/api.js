
const API_BASE = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      // Keep the default error message.
    }

    throw new Error(message);
  }

  return response.json();
}

export async function checkBackend() {
  return request("/api/health");
}

export async function getDocuments() {
  const result = await request("/api/documents");
  return result.documents;
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  return request("/api/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function getDocumentVersions(documentId) {
  const result = await request(
    `/api/documents/${encodeURIComponent(documentId)}/versions`
  );

  return result.versions;
}

export async function createChangeRequest(
  documentId,
  description,
  scope = "full"
) {
  const formData = new FormData();
  formData.append("description", description);
  formData.append("scope", scope);

  return request(
    `/api/documents/${encodeURIComponent(documentId)}/requests`,
    {
      method: "POST",
      body: formData,
    }
  );
}

export async function getChangeRequests(documentId) {
  const result = await request(
    `/api/documents/${encodeURIComponent(documentId)}/requests`
  );

  return result.requests;
}
