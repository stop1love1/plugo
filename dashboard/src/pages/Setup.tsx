import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSite } from "../lib/api";
import {
  Globe, Play, Square, RefreshCw, CheckCircle, XCircle,
  Clock, Database, Trash2, Power, PowerOff,
} from "lucide-react";
import api from "../lib/api";

// API helpers for crawl management
const toggleCrawl = (siteId: string, data: any) =>
  api.put(`/crawl/toggle/${siteId}`, data).then((r) => r.data);
const startCrawl = (data: any) =>
  api.post("/crawl/start", data).then((r) => r.data);
const stopCrawl = (siteId: string) =>
  api.post(`/crawl/stop/${siteId}`).then((r) => r.data);
const getCrawlStatus = (siteId: string) =>
  api.get(`/crawl/status/${siteId}`).then((r) => r.data);
const getCrawlJobs = (siteId: string) =>
  api.get(`/crawl/jobs/${siteId}`).then((r) => r.data);
const clearKnowledge = (siteId: string) =>
  api.delete(`/crawl/knowledge/${siteId}`).then((r) => r.data);

export default function Setup() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const [maxPages, setMaxPages] = useState(50);
  const [customUrl, setCustomUrl] = useState("");

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: crawlStatus, refetch: refetchStatus } = useQuery({
    queryKey: ["crawl-status", siteId],
    queryFn: () => getCrawlStatus(siteId!),
    enabled: !!siteId,
    refetchInterval: (data) => data?.crawl_status === "running" ? 2000 : false,
  });

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ["crawl-jobs", siteId],
    queryFn: () => getCrawlJobs(siteId!),
    enabled: !!siteId,
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      toggleCrawl(siteId!, { enabled, max_pages: maxPages }),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
    },
  });

  const startMutation = useMutation({
    mutationFn: () =>
      startCrawl({
        site_id: siteId!,
        url: customUrl || undefined,
        max_pages: maxPages,
      }),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => stopCrawl(siteId!),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => clearKnowledge(siteId!),
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
    },
  });

  const isRunning = crawlStatus?.crawl_status === "running";
  const isEnabled = crawlStatus?.crawl_enabled ?? false;

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "failed": return <XCircle className="w-4 h-4 text-red-500" />;
      case "running": return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case "stopped": return <Square className="w-4 h-4 text-yellow-500" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Crawl & Knowledge</h1>
      <p className="text-gray-500 mb-8">Teach your bot by crawling your website content</p>

      {/* ========== Toggle Crawl ON/OFF ========== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {isEnabled ? (
              <Power className="w-6 h-6 text-green-500" />
            ) : (
              <PowerOff className="w-6 h-6 text-gray-400" />
            )}
            <div>
              <h3 className="font-semibold text-lg">
                Crawl: {isEnabled ? "ON" : "OFF"}
              </h3>
              <p className="text-sm text-gray-500">
                {isEnabled
                  ? "Bot is actively learning from your website"
                  : "Bot is not learning new content"}
              </p>
            </div>
          </div>

          <button
            onClick={() => toggleMutation.mutate(!isEnabled)}
            disabled={toggleMutation.isPending}
            className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors ${
              isEnabled ? "bg-green-500" : "bg-gray-300"
            }`}
          >
            <span
              className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform shadow ${
                isEnabled ? "translate-x-7" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mt-4 p-4 bg-gray-50 rounded-lg">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary-600">
              {crawlStatus?.knowledge_count ?? 0}
            </div>
            <div className="text-xs text-gray-500">Chunks Learned</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-700">
              {crawlStatus?.crawl_status === "running" ? (
                <RefreshCw className="w-6 h-6 text-blue-500 animate-spin mx-auto" />
              ) : (
                crawlStatus?.crawl_status ?? "idle"
              )}
            </div>
            <div className="text-xs text-gray-500">Status</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-medium text-gray-700">
              {crawlStatus?.last_crawled_at
                ? new Date(crawlStatus.last_crawled_at).toLocaleDateString()
                : "Never"}
            </div>
            <div className="text-xs text-gray-500">Last Crawled</div>
          </div>
        </div>
      </div>

      {/* ========== Manual Crawl ========== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5" /> Manual Crawl
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              URL (leave empty to use site URL: {site?.url})
            </label>
            <input
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              placeholder={site?.url || "https://example.com"}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Max Pages
            </label>
            <input
              type="number"
              value={maxPages}
              onChange={(e) => setMaxPages(parseInt(e.target.value) || 50)}
              min={1}
              max={500}
              className="w-32 border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="flex gap-3">
            {isRunning ? (
              <button
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
                className="flex items-center gap-2 bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600 disabled:opacity-50"
              >
                <Square className="w-4 h-4" />
                {stopMutation.isPending ? "Stopping..." : "Stop Crawl"}
              </button>
            ) : (
              <button
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
                className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                <Play className="w-4 h-4" />
                {startMutation.isPending ? "Starting..." : "Start Crawl"}
              </button>
            )}

            <button
              onClick={() => {
                if (confirm("Delete all learned data? This action cannot be undone.")) {
                  clearMutation.mutate();
                }
              }}
              disabled={clearMutation.isPending || isRunning}
              className="flex items-center gap-2 text-red-500 border border-red-200 px-4 py-2 rounded-lg hover:bg-red-50 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" />
              Clear All Knowledge
            </button>
          </div>
        </div>
      </div>

      {/* ========== Crawl History ========== */}
      {jobs.length > 0 && (
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" /> Crawl History
          </h3>
          <div className="space-y-3">
            {jobs.map((job: any) => (
              <div
                key={job.id}
                className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
              >
                <div className="flex items-center gap-3">
                  {statusIcon(job.status)}
                  <div>
                    <span className="text-sm font-medium capitalize">{job.status}</span>
                    <span className="text-xs text-gray-400 ml-2">
                      {job.pages_done} pages
                    </span>
                  </div>
                </div>
                <span className="text-xs text-gray-400">
                  {job.started_at
                    ? new Date(job.started_at).toLocaleString()
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
