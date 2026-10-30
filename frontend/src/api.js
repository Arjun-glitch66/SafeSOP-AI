// Set VITE_API_BASE in frontend/.env.local to point at a different backend.
// An empty VITE_API_BASE (the Docker build) means same origin: nginx proxies /api to the backend.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "safesop.token";

// Storage can be blocked (private mode, policies); signing in then lasts until the tab closes.
let memoryToken = null;
export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) ?? memoryToken; } catch { return memoryToken; }
}
export function setToken(token) {
  memoryToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* memory only */ }
}

// Called on any 401 from a signed-in request (expired or revoked session). Set by AuthProvider.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) { onUnauthorized = handler; }

async function send(path, { auth = true, ...options } = {}) {
  const headers = { ...options.headers };
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!response.ok) {
    if (response.status === 401 && auth) {
      setToken(null);
      onUnauthorized();
    }
    let message = `Request failed (${response.status})`;
    try {
      const error = await response.json();
      // FastAPI validation errors (422) arrive as a list of {loc, msg}.
      message = Array.isArray(error.detail)
        ? error.detail.map((item) => `${item.loc?.at(-1)}: ${item.msg}`).join("; ")
        : error.detail || message;
    } catch {
      // Keep the default error message.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response;
}

async function request(path, options) {
  return (await send(path, options)).json();
}

function form(fields) {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null) data.append(key, value);
  }
  return data;
}

const id = encodeURIComponent;

// ---- auth ----
export async function login(username, password) {
  const result = await request("/api/auth/login", {
    auth: false, method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  setToken(result.access_token);
  return result.user;
}
export const getMe = () => request("/api/auth/me");

// ---- backend status ----
export const checkBackend = () => request("/api/health", { auth: false });
export const getEvaluationStatus = () => request("/api/evaluation/status", { auth: false });

// ---- documents ----
export const getDocuments = async () => (await request("/api/documents")).documents;
export const getDocument = (documentId) => request(`/api/documents/${id(documentId)}`);
export const uploadDocument = (file, documentType = "") =>
  request("/api/documents/upload", { method: "POST", body: form({ file, document_type: documentType }) });
export const getChecklists = async () => (await request("/api/checklists")).checklists;
export const getDocumentVersions = async (documentId) =>
  (await request(`/api/documents/${id(documentId)}/versions`)).versions;

export const createChangeRequest = (documentId, description, scope = "full", targetPage = null, targetSection = null) =>
  request(`/api/documents/${id(documentId)}/requests`, {
    method: "POST", body: form({ description, scope, ...partFields(scope, targetPage, targetSection) }),
  });

// With requestId, the backend takes description, scope and page from that saved request.
// `signal` (AbortController) lets the user stop waiting for a long generation.
// Page scope sends a page number; section and step scope send the outline id (SEC2, S4).
function partFields(scope, targetPage, targetSection) {
  if (scope === "page") return { target_page: targetPage };
  if (scope === "section" || scope === "step") return { target_section: targetSection };
  return {};
}

export const getOutline = (documentId) => request(`/api/documents/${id(documentId)}/outline`);

export function generateRevision(documentId, { description, scope = "full", targetPage = null, targetSection = null, parentVersionId = null, requestId = null, signal } = {}) {
  const fields = requestId
    ? { request_id: requestId }
    : { description, scope, ...partFields(scope, targetPage, targetSection) };
  return request(`/api/documents/${id(documentId)}/generate`, {
    method: "POST", signal, body: form({ ...fields, parent_version_id: parentVersionId }),
  });
}

// Follow a background job's server-sent events until it succeeds or fails. EventSource cannot
// send the Authorization header, so the stream is read with fetch. Resolves with the final job.
export async function followJob(jobId, onProgress, signal) {
  const response = await send(`/api/jobs/${id(jobId)}/events`, { signal });
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;  // keep-alive comment
      const job = JSON.parse(data);
      if (event === "progress") onProgress(job);
      else return job;
    }
  }
  return request(`/api/jobs/${id(jobId)}`);  // stream ended early: ask once more
}

// ---- versions ----
export const getVersion = (versionId) => request(`/api/versions/${id(versionId)}`);
export const getVersionContent = async (versionId) => (await request(`/api/versions/${id(versionId)}/content`)).content;
export const getVersionDiff = (versionId) => request(`/api/versions/${id(versionId)}/diff`);
export const getEvaluations = async (versionId) => (await request(`/api/versions/${id(versionId)}/evaluations`)).evaluations;
export const runEvaluation = (versionId) => request(`/api/versions/${id(versionId)}/evaluate`, { method: "POST" });
export const getReviews = async (versionId) => (await request(`/api/versions/${id(versionId)}/reviews`)).reviews;

// A reviewer's verdict on one automated finding: "true_problem" or "false_alarm".
export const setFindingFeedback = (evaluationId, findingIndex, verdict) =>
  request(`/api/evaluations/${id(evaluationId)}/findings/${findingIndex}/feedback`, { method: "PUT", body: form({ verdict }) });

// Approval needs the reviewer's password again (electronic signature).
export const createReview = (versionId, { decision, feedback = "", password }) =>
  request(`/api/versions/${id(versionId)}/reviews`, { method: "POST", body: form({ decision, feedback, password }) });

// Files need the auth header too, so they are fetched and saved instead of linked.
async function saveFile(path, filename) {
  const blob = await (await send(path)).blob();
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
export const downloadVersion = (versionId, versionNumber, format = "txt") =>
  saveFile(`/api/versions/${id(versionId)}/download?format=${format}`, `SafeSOP-v${versionNumber}.${format}`);
export const downloadOriginal = (documentId, filename) =>
  saveFile(`/api/documents/${id(documentId)}/original`, filename);
