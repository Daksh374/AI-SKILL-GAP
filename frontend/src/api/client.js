import axios from "axios";

const SESSION_KEY = "career_engine_session";

export function getSessionId() {
  let id = null;
  try {
    id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, id);
    }
  } catch {
    id = id || crypto.randomUUID();
  }
  return id;
}

// All requests go to our FastAPI backend (never directly to Tavily) so API keys stay server-side.
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || "/api", timeout: 180000 });
api.interceptors.request.use((config) => {
  config.headers["X-Session-ID"] = getSessionId();
  return config;
});

export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  if (err?.code === "ECONNABORTED") return "The request timed out.";
  if (!err?.response) return "Cannot reach the backend. Is the FastAPI server running on port 8000?";
  return err?.message || "Unexpected error";
}

export const Api = {
  health: () => api.get("/health").then((r) => r.data),
  roles: () => api.get("/roles").then((r) => r.data),
  modelReport: () => api.get("/model/report").then((r) => r.data),
  listResumes: () => api.get("/resumes").then((r) => r.data),
  getResume: (id) => api.get(`/resumes/${id}`).then((r) => r.data),
  deleteResume: (id) => api.delete(`/resumes/${id}`),
  uploadResume: (file, onProgress) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post("/resumes", form, { onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0) })
      .then((r) => r.data);
  },
  dashboard: (id, role) => api.get(`/resumes/${id}/dashboard`, { params: { role } }).then((r) => r.data),
  skillGap: (id, role) => api.get(`/resumes/${id}/skill-gap`, { params: { role } }).then((r) => r.data),
  market: (role, resumeId, refresh = false) =>
    api.post("/market", { role, resume_id: resumeId ?? null, refresh }).then((r) => r.data),
  getRoadmap: (id, role) => api.get(`/resumes/${id}/roadmap`, { params: { role } }).then((r) => r.data),
  createRoadmap: (id, body) => api.post(`/resumes/${id}/roadmap`, body).then((r) => r.data),
  updateProgress: (roadmapId, stageIndex, completed) =>
    api.patch(`/roadmaps/${roadmapId}/progress`, { stage_index: stageIndex, completed }).then((r) => r.data),
};
