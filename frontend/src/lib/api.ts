import axios, { AxiosError } from "axios";

// ============================================================
// Types — mirrors backend response shapes
// ============================================================

export type ApiError = {
  status: number;
  detail: string;
};

export type Site = {
  id: string;
  name: string;
  url: string;
  token: string;
  llm_provider: string;
  llm_model: string;
  primary_color: string;
  greeting: string;
  position: string;
  widget_title: string;
  dark_mode: string;
  show_branding: boolean;
  bot_avatar: string;
  header_subtitle: string;
  input_placeholder: string;
  auto_open_delay: number;
  bubble_size: string;
  allowed_domains: string;
  system_prompt: string;
  bot_rules: string;
  response_language: string; // "auto" | "vi" | "en"
  suggestions: string[];
  is_approved: boolean;
  crawl_enabled: boolean;
  crawl_auto_interval: number;
  crawl_max_pages: number;
  crawl_status: string;
  last_crawled_at: string | null;
  knowledge_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type CreateSiteData = {
  name: string;
  url: string;
  llm_provider?: string;
  llm_model?: string;
};

export type UpdateSiteData = Partial<Omit<Site, "id" | "token" | "created_at" | "updated_at">> & {
  suggestions?: string[];
};

export type ProviderModel = {
  id: string;
  name: string;
  description?: string;
};

export type Provider = {
  id: string;
  name: string;
  models: ProviderModel[];
  requires_key: boolean;
  has_key: boolean;
  key_status?: "working" | "invalid" | "missing" | "local";
};

export type KnowledgeChunk = {
  id: string;
  site_id: string;
  source_url: string | null;
  source_type: string;
  title: string;
  content: string;
  chunk_index: number;
  embedding_id: string | null;
  crawled_at: string | null;
};

export type KnowledgeListResponse = {
  chunks: KnowledgeChunk[];
  total: number;
  page: number;
  per_page: number;
};

export type Tool = {
  id: string;
  site_id: string;
  name: string;
  description: string;
  method: string;
  url: string;
  params_schema: Record<string, unknown>;
  headers: Record<string, unknown>;
  auth_type: string | null;
  auth_value: string | null;
  enabled: boolean;
  created_at: string | null;
};

export type CreateToolData = {
  site_id: string;
  name: string;
  description: string;
  method?: string;
  url: string;
  params_schema?: Record<string, unknown>;
  headers?: Record<string, unknown>;
  auth_type?: string;
  auth_value?: string;
};

export type UpdateToolData = Partial<Omit<Tool, "id" | "site_id" | "created_at">>;

export type ChatSession = {
  id: string;
  site_id: string;
  visitor_id: string;
  page_url?: string;
  first_message?: string;
  messages: { role: string; content: string; timestamp?: string; created_at?: string }[];
  message_count: number;
  started_at: string | null;
  ended_at: string | null;
};

export type CrawlStartData = {
  site_id: string;
  url?: string;
  max_pages?: number;
  max_depth?: number;
  force_recrawl?: boolean;
  exclude_patterns?: string;
};

export type CrawlJob = {
  id: string;
  site_id: string;
  status: string;
  start_url: string;
  pages_found: number;
  pages_done: number;
  pages_skipped: number;
  pages_failed: number;
  chunks_created: number;
  current_url: string | null;
  error_log: string | null;
  crawl_log: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type CrawlStatus = {
  site_id: string;
  crawl_enabled: boolean;
  crawl_status: string;
  crawl_auto_interval: number;
  crawl_max_pages: number;
  crawl_max_depth: number;
  crawl_exclude_patterns: string;
  knowledge_count: number;
  last_crawled_at: string | null;
  is_running: boolean;
  is_paused: boolean;
  current_url: string | null;
};

export type ManualChunkData = {
  site_id: string;
  title: string;
  content: string;
  source_url?: string;
};

export type LLMKeyInfo = {
  id: string;
  provider: string;
  api_key_masked: string;
  label: string;
  updated_at: string | null;
};

export type CrawledUrl = {
  source_url: string;
  chunk_count: number;
  title: string | null;
  last_crawled_at: string | null;
  source_type: string;
};

export type AuditLogEntry = {
  id: string;
  user_id: string;
  username: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: string | null;
  created_at: string;
};

export type AuditLogResponse = {
  logs: AuditLogEntry[];
  total: number;
  page: number;
  per_page: number;
};

// ============================================================
// Axios instance & interceptors
// ============================================================

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

// ============================================================
// API functions
// ============================================================

// Auth
export const login = (data: { username: string; password: string }) =>
  api.post<{ username: string; role: string; access_token: string }>("/auth/login", data).then((r) => r.data);
export const getMe = () => api.get<{ username: string; role: string }>("/auth/me").then((r) => r.data);

// Sites
export const getSites = () => api.get<Site[]>("/sites").then((r) => r.data);
export const getSite = (id: string) => api.get<Site>(`/sites/${id}`).then((r) => r.data);
export const createSite = (data: CreateSiteData) => api.post<Site>("/sites", data).then((r) => r.data);
export const updateSite = (id: string, data: UpdateSiteData) => api.put<Site>(`/sites/${id}`, data).then((r) => r.data);
export const deleteSite = (id: string) => api.delete<{ message: string }>(`/sites/${id}`).then((r) => r.data);
export const updateSiteApproval = (siteId: string, isApproved: boolean) =>
  api.put<Site>(`/sites/${siteId}/approval`, { is_approved: isApproved }).then((r) => r.data);
export const getProviders = () => api.get<Provider[]>("/sites/providers/list").then((r) => r.data);

// Crawl
export const startCrawl = (data: CrawlStartData) =>
  api.post<{ job_id: string; status: string; message: string; force_recrawl?: boolean }>("/crawl/start", data).then((r) => r.data);
export const stopCrawl = (siteId: string) =>
  api.post<{ message: string; crawl_status: string; knowledge_count: number }>(`/crawl/stop/${siteId}`).then((r) => r.data);
export const pauseCrawl = (siteId: string) =>
  api.post<{ message: string; crawl_status: string }>(`/crawl/pause/${siteId}`).then((r) => r.data);
export const resumeCrawl = (siteId: string) =>
  api.post<{ message: string; crawl_status: string }>(`/crawl/resume/${siteId}`).then((r) => r.data);
export const toggleCrawl = (siteId: string, data: { enabled: boolean; max_pages?: number; auto_interval?: number; max_depth?: number; exclude_patterns?: string }) =>
  api.put(`/crawl/toggle/${siteId}`, data).then((r) => r.data);
export const getCrawlSiteStatus = (siteId: string) =>
  api.get<CrawlStatus>(`/crawl/status/${siteId}`).then((r) => r.data);
export const getSiteCrawlJobs = (siteId: string) =>
  api.get<CrawlJob[]>(`/crawl/jobs/${siteId}`).then((r) => r.data);
export const getCrawlLogs = (jobId: string) =>
  api.get<{ logs: unknown[]; status: string; pages_done: number }>(`/crawl/job/${jobId}/logs`).then((r) => r.data);
export const updateCrawlSettings = (siteId: string, data: { max_pages?: number; max_depth?: number; auto_interval?: number; exclude_patterns?: string }) =>
  api.put(`/crawl/settings/${siteId}`, data).then((r) => r.data);

// Knowledge
export const clearAllKnowledge = (siteId: string) =>
  api.delete<{ message: string; knowledge_count: number }>(`/crawl/knowledge/${siteId}`).then((r) => r.data);
export const getKnowledge = (siteId: string, page = 1, search?: string) => {
  let url = `/knowledge?site_id=${siteId}&page=${page}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return api.get<KnowledgeListResponse>(url).then((r) => r.data);
};
export const getChunk = (id: string) => api.get<KnowledgeChunk>(`/knowledge/${id}`).then((r) => r.data);
export const updateChunk = (id: string, data: { title?: string; content?: string }) =>
  api.put<{ message: string; chunk: KnowledgeChunk }>(`/knowledge/${id}`, data).then((r) => r.data);
export const deleteChunk = (id: string) => api.delete<{ message: string }>(`/knowledge/${id}`).then((r) => r.data);
export const addManualChunk = (data: ManualChunkData) =>
  api.post<{ id: string; message: string; embedding: string }>("/knowledge/manual", data).then((r) => r.data);
export const uploadFile = (siteId: string, file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post<{ id: string; filename: string; message: string; embedding: string }>(`/knowledge/upload?site_id=${siteId}`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};

export const bulkDeleteChunks = (ids: string[]) =>
  api.post<{ deleted: number }>("/knowledge/bulk-delete", { chunk_ids: ids }).then((r) => r.data);

// Crawled URLs
export const getCrawledUrls = (siteId: string) =>
  api.get<CrawledUrl[]>(`/knowledge/urls?site_id=${siteId}`).then((r) => r.data);
export const getChunksByUrl = (siteId: string, sourceUrl: string) =>
  api.get<{ chunks: KnowledgeChunk[]; total: number }>(`/knowledge/url/chunks?site_id=${siteId}&source_url=${encodeURIComponent(sourceUrl)}`).then((r) => r.data);
export const deleteByUrl = (siteId: string, sourceUrl: string) =>
  api.post<{ deleted: number }>("/knowledge/url/delete", { site_id: siteId, source_url: sourceUrl }).then((r) => r.data);
export const recrawlUrl = (siteId: string, sourceUrl: string) =>
  api.post<{ message: string; old_chunks: number; new_chunks: number }>("/knowledge/url/recrawl", { site_id: siteId, source_url: sourceUrl }).then((r) => r.data);

// Tools
export const getTools = (siteId: string) => api.get<Tool[]>(`/tools?site_id=${siteId}`).then((r) => r.data);
export const createTool = (data: CreateToolData) => api.post<{ id: string; message: string }>("/tools", data).then((r) => r.data);
export const updateTool = (id: string, data: UpdateToolData) => api.put<{ message: string }>(`/tools/${id}`, data).then((r) => r.data);
export const deleteTool = (id: string) => api.delete<{ message: string }>(`/tools/${id}`).then((r) => r.data);
export const testTool = (id: string, params: Record<string, unknown>) =>
  api.post<{ status: number; response: unknown }>(`/tools/${id}/test`, { params }).then((r) => r.data);

// Sessions
export const getSessions = (siteId: string) =>
  api.get<ChatSession[]>(`/sessions?site_id=${siteId}`).then((r) => r.data);
export const getSession = (id: string) => api.get<ChatSession>(`/sessions/${id}`).then((r) => r.data);

// LLM Keys
export const getLLMKeys = () => api.get<LLMKeyInfo[]>("/llm-keys").then((r) => r.data);
export const saveLLMKey = (data: { provider: string; api_key: string; label?: string }) =>
  api.post<{ message: string; provider: string }>("/llm-keys", data).then((r) => r.data);
export const deleteLLMKey = (provider: string) =>
  api.delete<{ message: string }>(`/llm-keys/${provider}`).then((r) => r.data);

// Models
export type CustomModel = {
  provider: string;
  model_id: string;
  model_name: string;
  description: string;
};

export const getModelsProviders = () => api.get<Provider[]>("/models/providers").then((r) => r.data);
export const getCustomModels = () => api.get<CustomModel[]>("/models/custom").then((r) => r.data);
export const addCustomModel = (data: CustomModel) =>
  api.post<{ message: string; provider: string; model_id: string }>("/models/custom", data).then((r) => r.data);
export const deleteCustomModel = (provider: string, modelId: string) =>
  api.delete<{ message: string }>("/models/custom", { data: { provider, model_id: modelId } }).then((r) => r.data);

// Audit
export const getAuditLogs = (page = 1) =>
  api.get<AuditLogResponse>(`/audit?page=${page}`).then((r) => r.data);

// Feedback
export const submitFeedback = (sessionId: string, messageIndex: number, rating: "up" | "down") =>
  api.post<{ message: string }>(`/sessions/${sessionId}/feedback`, { message_index: messageIndex, rating }).then((r) => r.data);

// Global Config
export type GlobalConfig = Record<string, Record<string, unknown>>;
export const getGlobalConfig = () => api.get<GlobalConfig>("/config").then((r) => r.data);
export const updateGlobalConfig = (data: GlobalConfig) =>
  api.put<{ status: string; message: string }>("/config", data).then((r) => r.data);

export default api;
