import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Sites
export const getSites = () => api.get("/sites").then((r) => r.data);
export const getSite = (id: string) => api.get(`/sites/${id}`).then((r) => r.data);
export const createSite = (data: any) => api.post("/sites", data).then((r) => r.data);
export const updateSite = (id: string, data: any) => api.put(`/sites/${id}`, data).then((r) => r.data);
export const deleteSite = (id: string) => api.delete(`/sites/${id}`).then((r) => r.data);
export const getProviders = () => api.get("/sites/providers/list").then((r) => r.data);

// Crawl
export const startCrawl = (data: any) => api.post("/crawl", data).then((r) => r.data);
export const getCrawlStatus = (jobId: string) => api.get(`/crawl/${jobId}`).then((r) => r.data);
export const getSiteCrawlJobs = (siteId: string) => api.get(`/crawl/site/${siteId}`).then((r) => r.data);

// Knowledge
export const getKnowledge = (siteId: string, page = 1) =>
  api.get(`/knowledge?site_id=${siteId}&page=${page}`).then((r) => r.data);
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

export default api;
