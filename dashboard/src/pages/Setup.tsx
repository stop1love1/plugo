import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getSite } from "../lib/api";
import {
  Globe, Play, Square, RefreshCw, CheckCircle, XCircle,
  Clock, Database, Trash2, Power, PowerOff, Settings2,
} from "lucide-react";
import api from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { OnboardingChecklist } from "../components/OnboardingChecklist";
import { pushNotification } from "../components/NotificationBell";

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
  const { t } = useLocale();
  const [maxPages, setMaxPages] = useState(50);
  const [customUrl, setCustomUrl] = useState("");
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: crawlStatus, refetch: refetchStatus } = useQuery({
    queryKey: ["crawl-status", siteId],
    queryFn: () => getCrawlStatus(siteId!),
    enabled: !!siteId,
    refetchInterval: (query) => query.state.data?.crawl_status === "running" ? 2000 : false,
  });

  // Detect crawl completion/failure and push notification
  const prevCrawlStatus = useRef<string | null>(null);
  useEffect(() => {
    const current = crawlStatus?.crawl_status;
    const prev = prevCrawlStatus.current;
    if (prev === "running" && current && current !== "running") {
      if (current === "completed" || current === "idle") {
        pushNotification({
          type: "success",
          title: t("notifications.crawlComplete"),
          message: `${crawlStatus?.knowledge_count ?? 0} chunks learned`,
        });
      } else if (current === "failed") {
        pushNotification({
          type: "error",
          title: t("notifications.crawlFailed"),
        });
      }
    }
    prevCrawlStatus.current = current ?? null;
  }, [crawlStatus?.crawl_status]);

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ["crawl-jobs", siteId],
    queryFn: () => getCrawlJobs(siteId!),
    enabled: !!siteId,
  });

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      toggleCrawl(siteId!, { enabled, max_pages: maxPages }),
    onSuccess: (_data, enabled) => {
      refetchStatus();
      refetchJobs();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      toast.success(enabled ? "Crawl enabled" : "Crawl disabled");
    },
    onError: () => toast.error("Failed to toggle crawl"),
  });

  const startMutation = useMutation({
    mutationFn: () =>
      startCrawl({ site_id: siteId!, url: customUrl || undefined, max_pages: maxPages }),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
      toast.success("Crawl started");
    },
    onError: () => toast.error("Failed to start crawl"),
  });

  const stopMutation = useMutation({
    mutationFn: () => stopCrawl(siteId!),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
      toast.success("Crawl stopped");
    },
    onError: () => toast.error("Failed to stop crawl"),
  });

  const clearMutation = useMutation({
    mutationFn: () => clearKnowledge(siteId!),
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      setShowClearConfirm(false);
      toast.success("All knowledge cleared");
    },
    onError: () => toast.error("Failed to clear knowledge"),
  });

  const isRunning = crawlStatus?.crawl_status === "running";
  const isEnabled = crawlStatus?.crawl_enabled ?? false;

  // Progress estimate for running crawls
  const runningJob = jobs.find((j: any) => j.status === "running");
  const progressPercent = runningJob && maxPages > 0
    ? Math.min(100, Math.round((runningJob.pages_done / maxPages) * 100))
    : 0;

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
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("setup.title")}</h1>
      <p className="text-gray-500 mb-6">{t("setup.subtitle")}</p>

      {/* Onboarding Checklist */}
      <OnboardingChecklist />

      {/* ===== SECTION 1: Auto Crawl Settings ===== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="w-5 h-5 text-gray-400" />
          <h3 className="font-semibold text-lg">{t("setup.autoCrawl")}</h3>
        </div>

        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {isEnabled ? (
              <Power className="w-6 h-6 text-green-500" />
            ) : (
              <PowerOff className="w-6 h-6 text-gray-400" />
            )}
            <div>
              <p className="font-medium">
                Crawl: {isEnabled ? "ON" : "OFF"}
              </p>
              <p className="text-sm text-gray-500">
                {isEnabled ? t("setup.autoCrawlDesc") : t("setup.autoCrawlOff")}
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
        <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary-600">
              {crawlStatus?.knowledge_count ?? 0}
            </div>
            <div className="text-xs text-gray-500">{t("setup.chunksLearned")}</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-700">
              {isRunning ? (
                <RefreshCw className="w-6 h-6 text-blue-500 animate-spin mx-auto" />
              ) : (
                crawlStatus?.crawl_status ?? "idle"
              )}
            </div>
            <div className="text-xs text-gray-500">{t("setup.status")}</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-medium text-gray-700">
              {crawlStatus?.last_crawled_at
                ? new Date(crawlStatus.last_crawled_at).toLocaleDateString()
                : t("setup.never")}
            </div>
            <div className="text-xs text-gray-500">{t("setup.lastCrawled")}</div>
          </div>
        </div>

        {/* Progress bar when running */}
        {isRunning && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-sm text-gray-600 mb-1">
              <span>{t("setup.crawlProgress")}</span>
              <span>{runningJob?.pages_done ?? 0} / {maxPages} {t("setup.pages")}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-primary-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* ===== SECTION 2: Manual Actions ===== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5" /> {t("setup.manualActions")}
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Manually trigger a crawl or clear learned data.
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t("setup.crawlUrl").replace("{url}", site?.url || "")}
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
              {t("setup.maxPages")}
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value))}
                min={1}
                max={500}
                className="flex-1"
              />
              <input
                type="number"
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value) || 50)}
                min={1}
                max={500}
                className="w-20 border border-gray-300 rounded-lg px-2 py-1 text-sm text-center outline-none"
              />
            </div>
          </div>
          <div className="flex gap-3">
            {isRunning ? (
              <button
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
                className="flex items-center gap-2 bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600 disabled:opacity-50"
              >
                <Square className="w-4 h-4" />
                {stopMutation.isPending ? "Stopping..." : t("setup.stopCrawl")}
              </button>
            ) : (
              <button
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
                className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                <Play className="w-4 h-4" />
                {startMutation.isPending ? "Starting..." : t("setup.startCrawl")}
              </button>
            )}

            {showClearConfirm ? (
              <div className="flex items-center gap-2">
                <span className="text-sm text-red-600">{t("setup.clearConfirm")}</span>
                <button
                  onClick={() => clearMutation.mutate()}
                  disabled={clearMutation.isPending}
                  className="text-sm bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                >
                  {t("common.confirm")}
                </button>
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  {t("common.cancel")}
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowClearConfirm(true)}
                disabled={clearMutation.isPending || isRunning}
                className="flex items-center gap-2 text-red-500 border border-red-200 px-4 py-2 rounded-lg hover:bg-red-50 disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                {t("setup.clearAll")}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ===== SECTION 3: Crawl History ===== */}
      {jobs.length > 0 && (
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" /> {t("setup.crawlHistory")}
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
                      {job.pages_done} {t("setup.pages")}
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
