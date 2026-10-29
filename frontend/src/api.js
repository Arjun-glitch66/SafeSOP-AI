// Set VITE_API_BASE in frontend/.env.local to point at a different backend.
const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

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

export async function generateRevision(documentId, description, scope = "full", targetPage = null, parentVersionId = null) {
  const formData = new FormData();
  formData.append("description", description);
  formData.append("scope", scope);
  if (scope === "page") formData.append("target_page", targetPage);
  if (parentVersionId) formData.append("parent_version_id", parentVersionId);

  return request(
    `/api/documents/${encodeURIComponent(documentId)}/generate`,
    {
      method: "POST",
      body: formData,
    }
  );
}

export async function getVersionContent(versionId) {
  const result = await request(
    `/api/versions/${encodeURIComponent(versionId)}/content`
  );

  return result.content;
}

export function versionDownloadUrl(versionId, format = "txt") {
  return `${API_BASE}/api/versions/${encodeURIComponent(versionId)}/download?format=${format}`;
}

export async function getVersionDiff(versionId) {
  return request(`/api/versions/${encodeURIComponent(versionId)}/diff`);
}

export async function getEvaluationStatus() {
  return request("/api/evaluation/status");
}

export async function getDocument(documentId) {
  return request(`/api/documents/${encodeURIComponent(documentId)}`);
}

export async function getEvaluations(versionId) {
  const result = await request(
    `/api/versions/${encodeURIComponent(versionId)}/evaluations`
  );

  return result.evaluations;
}

export async function runEvaluation(versionId) {
  return request(`/api/versions/${encodeURIComponent(versionId)}/evaluate`, {
    method: "POST",
  });
}

export async function getReviews(versionId) {
  const result = await request(
    `/api/versions/${encodeURIComponent(versionId)}/reviews`
  );

  return result.reviews;
}

export async function createReview(versionId, decision, reviewer, feedback) {
  const formData = new FormData();
  formData.append("decision", decision);
  formData.append("reviewer", reviewer);
  formData.append("feedback", feedback);

  return request(`/api/versions/${encodeURIComponent(versionId)}/reviews`, {
    method: "POST",
    body: formData,
  });
}

export function originalDownloadUrl(documentId) {
  return `${API_BASE}/api/documents/${encodeURIComponent(documentId)}/original`;
}

export async function getChangeRequests(documentId) {
  const result = await request(
    `/api/documents/${encodeURIComponent(documentId)}/requests`
  );

  return result.requests;
}
