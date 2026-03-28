import axios, { AxiosError } from "axios";

/** Typed API error from backend */
export type ApiError = {
  status: number;
  detail: string;
};

/** Extract a readable error message from any axios error */
export function getErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d: { msg: string }) => d.msg).join(", ");
    if (error.response?.status === 413) return "File too large";
    if (error.response?.status === 429) return "Too many requests. Please slow down.";
    if (error.response?.status === 500) return "Server error. Please try again later.";
    if (error.message) return error.message;
  }
  return "An unexpected error occurred";
}

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Auth interceptor — attach JWT token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("plugo_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 401 interceptor — redirect to login on auth failure
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config.url?.includes("/auth/")) {
      localStorage.removeItem("plugo_token");
      localStorage.removeItem("plugo_user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (data: { username: string; password: string }) =>
  api.post("/auth/login", data).then((r) => r.data);
export const getMe = () => api.get("/auth/me").then((r) => r.data);
export const getSetupStatus = () => api.get("/auth/setup-status").then((r) => r.data);

// Sites
export const getSites = () => api.get("/sites").then((r) => r.data);
export const getSite = (id: string) => api.get(`/sites/${id}`).then((r) => r.data);
export const createSite = (data: any) => api.post("/sites", data).then((r) => r.data);
export const updateSite = (id: string, data: any) => api.put(`/sites/${id}`, data).then((r) => r.data);
export const deleteSite = (id: string) => api.delete(`/sites/${id}`).then((r) => r.data);
export const updateSiteApproval = (siteId: string, isApproved: boolean) =>
  api.put(`/sites/${siteId}/approval`, { is_approved: isApproved }).then((r) => r.data);
export const getProviders = () => api.get("/sites/providers/list").then((r) => r.data);

// Crawl
export const startCrawl = (data: any) => api.post("/crawl", data).then((r) => r.data);
export const getCrawlStatus = (jobId: string) => api.get(`/crawl/${jobId}`).then((r) => r.data);
export const getSiteCrawlJobs = (siteId: string) => api.get(`/crawl/site/${siteId}`).then((r) => r.data);
export const getCrawlLogs = (jobId: string) =>
  api.get(`/crawl/job/${jobId}/logs`).then((r) => r.data);

// Knowledge
export const getKnowledge = (siteId: string, page = 1, search?: string) => {
  let url = `/knowledge?site_id=${siteId}&page=${page}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return api.get(url).then((r) => r.data);
};
export const getChunk = (id: string) => api.get(`/knowledge/${id}`).then((r) => r.data);
export const updateChunk = (id: string, data: { title?: string; content?: string }) =>
  api.put(`/knowledge/${id}`, data).then((r) => r.data);
export const deleteChunk = (id: string) => api.delete(`/knowledge/${id}`).then((r) => r.data);
export const addManualChunk = (data: any) => api.post("/knowledge/manual", data).then((r) => r.data);
export const uploadFile = (siteId: string, file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post(`/knowledge/upload?site_id=${siteId}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};

// Tools
export const getTools = (siteId: string) => api.get(`/tools?site_id=${siteId}`).then((r) => r.data);
export const createTool = (data: any) => api.post("/tools", data).then((r) => r.data);
export const updateTool = (id: string, data: any) => api.put(`/tools/${id}`, data).then((r) => r.data);
export const deleteTool = (id: string) => api.delete(`/tools/${id}`).then((r) => r.data);
export const testTool = (id: string, params: any) =>
  api.post(`/tools/${id}/test`, { params }).then((r) => r.data);

// Sessions
export const getSessions = (siteId: string) =>
  api.get(`/sessions?site_id=${siteId}`).then((r) => r.data);
export const getSession = (id: string) => api.get(`/sessions/${id}`).then((r) => r.data);

// Users
export const getUsers = () => api.get("/users").then((r) => r.data);
export const createUser = (data: { username: string; password: string; role: string }) =>
  api.post("/users", data).then((r) => r.data);
export const updateUserRole = (id: string, role: string) =>
  api.put(`/users/${id}/role`, { role }).then((r) => r.data);
export const deleteUser = (id: string) => api.delete(`/users/${id}`).then((r) => r.data);

// LLM Keys
export const getLLMKeys = () => api.get("/llm-keys").then((r) => r.data);
export const saveLLMKey = (data: { provider: string; api_key: string; label?: string }) =>
  api.post("/llm-keys", data).then((r) => r.data);
export const deleteLLMKey = (provider: string) =>
  api.delete(`/llm-keys/${provider}`).then((r) => r.data);

// Audit
export const getAuditLogs = (page = 1) =>
  api.get(`/audit?page=${page}`).then((r) => r.data);

// Feedback
export const submitFeedback = (sessionId: string, messageIndex: number, rating: "up" | "down") =>
  api.post(`/sessions/${sessionId}/feedback`, { message_index: messageIndex, rating }).then((r) => r.data);

export default api;
