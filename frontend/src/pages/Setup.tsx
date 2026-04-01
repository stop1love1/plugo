import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getSite } from "../lib/api";
import {
  Globe, Play, Square, RefreshCw, CheckCircle, XCircle,
  Clock, Database, Trash2, Power, PowerOff, Settings2,
  ChevronDown, ChevronUp, Terminal, Link, FileText, AlertTriangle,
  Pause, SkipForward, Filter, Layers, Zap,
} from "lucide-react";
import api from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { OnboardingChecklist } from "../components/OnboardingChecklist";
import { pushNotification } from "../lib/notifications";

// API calls
const toggleCrawl = (siteId: string, data: { enabled: boolean; max_pages?: number; auto_interval?: number; max_depth?: number; exclude_patterns?: string }) =>
  api.put(`/crawl/toggle/${siteId}`, data).then((r) => r.data);
const startCrawl = (data: { site_id: string; url?: string; max_pages?: number; max_depth?: number; force_recrawl?: boolean; exclude_patterns?: string }) =>
  api.post("/crawl/start", data).then((r) => r.data);
const stopCrawl = (siteId: string) =>
  api.post(`/crawl/stop/${siteId}`).then((r) => r.data);
const pauseCrawl = (siteId: string) =>
  api.post(`/crawl/pause/${siteId}`).then((r) => r.data);
const resumeCrawl = (siteId: string) =>
  api.post(`/crawl/resume/${siteId}`).then((r) => r.data);
const getCrawlStatus = (siteId: string) =>
  api.get(`/crawl/status/${siteId}`).then((r) => r.data);
const getCrawlJobs = (siteId: string) =>
  api.get(`/crawl/jobs/${siteId}`).then((r) => r.data);
const clearKnowledge = (siteId: string) =>
  api.delete(`/crawl/knowledge/${siteId}`).then((r) => r.data);
const getCrawlLogs = (jobId: string) =>
  api.get(`/crawl/job/${jobId}/logs`).then((r) => r.data);
const updateCrawlSettings = (siteId: string, data: Record<string, unknown>) =>
  api.put(`/crawl/settings/${siteId}`, data).then((r) => r.data);

type LogEntry = {
  url: string;
  status: "success" | "skipped" | "error";
  title?: string;
  chunks: number;
  error?: string | null;
  action?: string;
  page_number?: number;
  timestamp: string;
};

export default function Setup() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [maxPages, setMaxPages] = useState(50);
  const [maxDepth, setMaxDepth] = useState(0);
  const [customUrl, setCustomUrl] = useState("");
  const [autoInterval, setAutoInterval] = useState(0);
  const [excludePatterns, setExcludePatterns] = useState("");
  const [forceRecrawl, setForceRecrawl] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [selectedLogJobId, setSelectedLogJobId] = useState<string | null>(null);
  const [logsExpanded, setLogsExpanded] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: crawlStatus, refetch: refetchStatus } = useQuery({
    queryKey: ["crawl-status", siteId],
    queryFn: () => getCrawlStatus(siteId!),
    enabled: !!siteId,
    refetchInterval: (query) => {
      const status = query.state.data?.crawl_status;
      return status === "running" || status === "paused" ? 2000 : false;
    },
  });

  // Sync settings from server
  useEffect(() => {
    if (crawlStatus) {
      if (crawlStatus.crawl_auto_interval !== undefined) setAutoInterval(crawlStatus.crawl_auto_interval);
      if (crawlStatus.crawl_max_depth !== undefined) setMaxDepth(crawlStatus.crawl_max_depth);
      if (crawlStatus.crawl_exclude_patterns !== undefined) setExcludePatterns(crawlStatus.crawl_exclude_patterns);
      if (crawlStatus.crawl_max_pages !== undefined) setMaxPages(crawlStatus.crawl_max_pages);
    }
  }, [
    crawlStatus,
    crawlStatus?.crawl_auto_interval,
    crawlStatus?.crawl_max_depth,
    crawlStatus?.crawl_exclude_patterns,
    crawlStatus?.crawl_max_pages,
  ]);

  // Tick every second while crawl is running
  useEffect(() => {
    if (crawlStatus?.crawl_status !== "running") return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [crawlStatus?.crawl_status]);

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ["crawl-jobs", siteId],
    queryFn: () => getCrawlJobs(siteId!),
    enabled: !!siteId,
  });

  // Detect crawl completion/failure and push notification + refresh jobs
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
      refetchJobs();
    }
    prevCrawlStatus.current = current ?? null;
  }, [crawlStatus?.crawl_status, crawlStatus?.knowledge_count, t, refetchJobs]);

  // Find the running/paused job
  const activeJob = jobs.find((j: { status: string }) => j.status === "running" || j.status === "paused");

  // Determine which job to show logs for
  const activeLogJobId = activeJob?.id || selectedLogJobId;

  const { data: logData } = useQuery({
    queryKey: ["crawl-logs", activeLogJobId],
    queryFn: () => getCrawlLogs(activeLogJobId!),
    enabled: !!activeLogJobId,
    refetchInterval: activeJob?.id === activeLogJobId && activeJob?.status === "running" ? 2000 : false,
  });

  // Auto-scroll log container
  useEffect(() => {
    if (logContainerRef.current && logsExpanded) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logData?.logs?.length, logsExpanded]);

  // Clear selected log job when a new crawl starts
  useEffect(() => {
    if (activeJob?.id) {
      setSelectedLogJobId(null);
    }
  }, [activeJob?.id]);

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) => {
      const interval = enabled && autoInterval === 0 ? 24 : autoInterval;
      if (enabled && autoInterval === 0) setAutoInterval(24);
      return toggleCrawl(siteId!, {
        enabled,
        max_pages: maxPages,
        auto_interval: interval,
        max_depth: maxDepth,
        exclude_patterns: excludePatterns,
      });
    },
    onSuccess: (_data, enabled) => {
      refetchStatus();
      refetchJobs();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      toast.success(enabled ? t("setup.crawlEnabled") : t("setup.crawlDisabled"));
    },
    onError: () => toast.error(t("setup.toggleFailed")),
  });

  const startMutation = useMutation({
    mutationFn: () =>
      startCrawl({
        site_id: siteId!,
        url: customUrl || undefined,
        max_pages: maxPages,
        max_depth: maxDepth,
        force_recrawl: forceRecrawl || undefined,
        exclude_patterns: excludePatterns || undefined,
      }),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
      toast.success(forceRecrawl ? t("setup.crawlStartedForce") : t("setup.crawlStarted"));
      setForceRecrawl(false);
    },
    onError: () => toast.error(t("setup.startFailed")),
  });

  const stopMutation = useMutation({
    mutationFn: () => stopCrawl(siteId!),
    onSuccess: () => {
      refetchStatus();
      refetchJobs();
      toast.success(t("setup.crawlStopped"));
    },
    onError: () => toast.error(t("setup.stopFailed")),
  });

  const pauseMutation = useMutation({
    mutationFn: () => pauseCrawl(siteId!),
    onSuccess: () => {
      refetchStatus();
      toast.success(t("setup.crawlPaused"));
    },
    onError: () => toast.error(t("setup.pauseFailed")),
  });

  const resumeMutation = useMutation({
    mutationFn: () => resumeCrawl(siteId!),
    onSuccess: () => {
      refetchStatus();
      toast.success(t("setup.crawlResumed"));
    },
    onError: () => toast.error(t("setup.resumeFailed")),
  });

  const clearMutation = useMutation({
    mutationFn: () => clearKnowledge(siteId!),
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      setShowClearConfirm(false);
      toast.success(t("setup.knowledgeCleared"));
    },
    onError: () => toast.error(t("setup.clearFailed")),
  });

  const isRunning = crawlStatus?.crawl_status === "running";
  const isPaused = crawlStatus?.crawl_status === "paused";
  const isActive = isRunning || isPaused;
  const isEnabled = crawlStatus?.crawl_enabled ?? false;

  const progressPercent = activeJob && maxPages > 0
    ? Math.min(100, Math.round((activeJob.pages_done / maxPages) * 100))
    : 0;

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "failed": return <XCircle className="w-4 h-4 text-red-500" />;
      case "running": return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case "paused": return <Pause className="w-4 h-4 text-amber-500" />;
      case "stopped": return <Square className="w-4 h-4 text-yellow-500" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const renderLogEntry = (log: LogEntry) => {
    const isSystem = !log.url;
    return (
      <div className="flex items-start gap-2 py-1 border-b border-gray-800 last:border-0">
        <span className="text-gray-500 shrink-0 w-[70px]">
          {new Date(log.timestamp).toLocaleTimeString()}
        </span>
        {isSystem ? (
          <span className="text-cyan-400 shrink-0">SYS</span>
        ) : log.status === "success" ? (
          <span className="text-green-400 shrink-0">OK </span>
        ) : log.status === "skipped" ? (
          <span className="text-yellow-400 shrink-0">SKP</span>
        ) : (
          <span className="text-red-400 shrink-0">ERR</span>
        )}
        {isSystem ? (
          <span className="text-cyan-300 flex-1">{log.action}</span>
        ) : (
          <>
            <span className="text-gray-300 truncate flex-1" title={`${log.url}\n${log.title || ""}`}>
              {log.title ? `${log.title} — ` : ""}{log.url}
            </span>
            {log.status === "success" && log.chunks > 0 && (
              <span className="text-blue-400 shrink-0">{log.chunks} chunks</span>
            )}
            {log.action && !log.error && log.status !== "success" && (
              <span className="text-gray-500 shrink-0 text-[10px]">{log.action}</span>
            )}
            {log.error && (
              <span className="text-red-400 shrink-0 truncate max-w-[200px]" title={log.error}>
                {log.error}
              </span>
            )}
          </>
        )}
      </div>
    );
  };

  // Save settings debounced
  const saveSettings = (data: Record<string, unknown>) => {
    if (siteId) updateCrawlSettings(siteId, data).catch(() => {});
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("setup.title")}</h1>
      <p className="text-gray-500 mb-6">{t("setup.subtitle")}</p>

      <OnboardingChecklist />

      {/* ===== SECTION 1: Auto Crawl Settings ===== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="w-5 h-5 text-gray-400" />
          <h3 className="font-semibold text-lg">{t("setup.autoCrawl")}</h3>
        </div>

        {/* Settings always visible — before toggle */}
        <div className="mb-4 p-3 bg-gray-50 rounded-lg border border-gray-100 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t("setup.maxPages")}
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={1}
                max={500}
                value={maxPages}
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10);
                  setMaxPages(val);
                  updateCrawlSettings(siteId!, { max_pages: val }).then(() => {
                    refetchStatus();
                  });
                }}
                className="flex-1 accent-primary-500"
              />
              <input
                type="number"
                value={maxPages}
                onChange={(e) => {
                  const val = Math.max(1, Math.min(500, parseInt(e.target.value) || 50));
                  setMaxPages(val);
                  updateCrawlSettings(siteId!, { max_pages: val }).then(() => {
                    refetchStatus();
                  });
                }}
                min={1}
                max={500}
                className="w-16 border border-gray-300 rounded-lg px-2 py-1 text-sm text-center outline-none"
              />
              <span className="text-xs text-gray-500">{t("setup.pages")}</span>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t("setup.autoInterval")}
            </label>
            <div className="flex items-center gap-3">
              <select
                value={autoInterval}
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10);
                  setAutoInterval(val);
                  updateCrawlSettings(siteId!, { auto_interval: val }).then(() => {
                    refetchStatus();
                  });
                }}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm outline-none bg-white"
              >
                <option value={0}>{t("setup.intervalDisabled")}</option>
                <option value={6}>6h</option>
                <option value={12}>12h</option>
                <option value={24}>24h</option>
                <option value={48}>48h</option>
                <option value={168}>{t("setup.intervalWeekly")}</option>
              </select>
              {autoInterval > 0 && (
                <span className="text-xs text-gray-500">
                  {t("setup.autoIntervalDesc")}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Toggle ON/OFF */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {isEnabled ? (
              isActive ? (
                <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
              ) : (
                <Power className="w-6 h-6 text-green-500" />
              )
            ) : (
              <PowerOff className="w-6 h-6 text-gray-400" />
            )}
            <div>
              <p className="font-medium">
                {t("setup.crawlToggle")}: {isEnabled ? "ON" : "OFF"}
              </p>
              <p className="text-sm text-gray-500">
                {isEnabled
                  ? isActive
                    ? t("setup.crawlingNow")
                    : t("setup.autoCrawlDesc")
                  : t("setup.autoCrawlOff")}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Quick "Run Now" when enabled but idle */}
            {isEnabled && !isActive && (
              <button
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
                className="flex items-center gap-1.5 text-sm text-blue-600 bg-blue-50 border border-blue-200 px-3 py-1.5 rounded-lg hover:bg-blue-100 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" />
                {t("setup.runNow")}
              </button>
            )}
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
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
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
              ) : isPaused ? (
                <Pause className="w-6 h-6 text-amber-500 mx-auto" />
              ) : (
                <span className="capitalize">{crawlStatus?.crawl_status ?? "idle"}</span>
              )}
            </div>
            <div className="text-xs text-gray-500">{t("setup.status")}</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-medium text-gray-700">
              {activeJob ? `${activeJob.pages_done}` : "—"}
              {activeJob && <span className="text-gray-400 text-xs">/{maxPages}</span>}
            </div>
            <div className="text-xs text-gray-500">{t("setup.pagesCrawled")}</div>
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

        {/* Live progress when running or paused */}
        {isActive && (
          <div className="mt-4">
            {/* Current URL indicator */}
            {crawlStatus?.current_url && (
              <div className="flex items-center gap-2 mb-2 px-1">
                <Link className={`w-3.5 h-3.5 shrink-0 ${isPaused ? "text-amber-500" : "text-blue-500 animate-pulse"}`} />
                <span className={`text-xs truncate ${isPaused ? "text-amber-600" : "text-blue-600"}`} title={crawlStatus.current_url}>
                  {isPaused ? t("setup.pausedAt") : t("setup.crawlingNow")}: {crawlStatus.current_url}
                </span>
              </div>
            )}

            {/* Progress bar */}
            <div className="flex items-center justify-between text-sm text-gray-600 mb-1">
              <span>{t("setup.crawlProgress")}{isPaused ? ` (${t("setup.paused")})` : ""}</span>
              <span>
                {activeJob?.pages_done ?? 0} / {maxPages} {t("setup.pages")}
                {activeJob?.pages_skipped > 0 && (
                  <span className="text-yellow-500 ml-2">({activeJob.pages_skipped} {t("setup.skipped")})</span>
                )}
                {activeJob?.pages_failed > 0 && (
                  <span className="text-red-500 ml-2">({activeJob.pages_failed} {t("setup.failed")})</span>
                )}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className={`h-2.5 rounded-full transition-all duration-500 ${isPaused ? "bg-amber-500" : "bg-primary-600"}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            {activeJob?.started_at && (
              <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {t("setup.elapsed")}: {(() => {
                    const elapsed = Math.max(0, Math.floor((now - new Date(activeJob.started_at).getTime()) / 1000));
                    const mins = Math.floor(elapsed / 60);
                    const secs = elapsed % 60;
                    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
                  })()}
                </span>
                <span>
                  {t("setup.speed")}: {(() => {
                    const elapsedMin = Math.max(0, (now - new Date(activeJob.started_at).getTime()) / 60000);
                    if (elapsedMin < 0.1) return t("setup.calculating");
                    return `${(activeJob.pages_done / elapsedMin).toFixed(1)} ${t("setup.pagesPerMin")}`;
                  })()}
                </span>
                {activeJob?.chunks_created > 0 && (
                  <span className="flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {activeJob.chunks_created} {t("setup.chunksCreated")}
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Crawl Log Panel */}
        {(isActive || selectedLogJobId) && logData?.logs?.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setLogsExpanded(!logsExpanded)}
              className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 mb-2"
            >
              <Terminal className="w-4 h-4" />
              <span className="font-medium">{t("setup.crawlLog")} ({logData.logs.length} {t("setup.entries")})</span>
              {logsExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {logsExpanded && (
              <div
                ref={logContainerRef}
                className="bg-gray-900 rounded-lg p-4 max-h-80 overflow-y-auto font-mono text-xs"
              >
                {logData.logs.map((log: LogEntry, i: number) => (
                  <div key={`${log.timestamp}-${log.url || i}`}>
                    {renderLogEntry(log)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ===== SECTION 2: Manual Scan ===== */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5" /> {t("setup.manualActions")}
        </h3>

        {/* Site URL info */}
        <div className="flex items-center gap-2 p-3 mb-4 bg-gray-50 rounded-lg border border-gray-100">
          <Globe className="w-4 h-4 text-gray-400 shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="text-xs text-gray-500">{t("setup.siteUrl")}</div>
            <div className="text-sm font-medium text-gray-900 truncate">{site?.url || "—"}</div>
          </div>
          <span className="text-[10px] text-gray-400 shrink-0">{t("setup.autoTarget")}</span>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          {t("setup.manualActionsDesc")}
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t("setup.scanUrl")}
            </label>
            <input
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
              placeholder={site?.url || "https://example.com"}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
            <p className="text-xs text-gray-400 mt-1">{t("setup.scanUrlHint")}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t("setup.maxPages")}
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                value={maxPages}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  setMaxPages(val);
                  saveSettings({ max_pages: val });
                }}
                min={1}
                max={500}
                className="flex-1"
              />
              <input
                type="number"
                value={maxPages}
                onChange={(e) => {
                  const val = parseInt(e.target.value) || 50;
                  setMaxPages(val);
                  saveSettings({ max_pages: val });
                }}
                min={1}
                max={500}
                className="w-20 border border-gray-300 rounded-lg px-2 py-1 text-sm text-center outline-none"
              />
            </div>
          </div>

          {/* Advanced Settings Toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700"
          >
            <Settings2 className="w-4 h-4" />
            <span>{t("setup.advancedSettings")}</span>
            {showAdvanced ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>

          {showAdvanced && (
            <div className="space-y-4 p-4 bg-gray-50 rounded-lg border border-gray-100">
              {/* Max Depth */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
                  <Layers className="w-4 h-4 text-gray-400" />
                  {t("setup.maxDepth")}
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    value={maxDepth}
                    onChange={(e) => {
                      const val = Math.max(0, parseInt(e.target.value) || 0);
                      setMaxDepth(val);
                      saveSettings({ max_depth: val });
                    }}
                    min={0}
                    max={20}
                    className="w-20 border border-gray-300 rounded-lg px-2 py-1 text-sm text-center outline-none"
                  />
                  <span className="text-xs text-gray-400">
                    {maxDepth === 0 ? t("setup.depthUnlimited") : `${maxDepth} ${t("setup.depthLevels")}`}
                  </span>
                </div>
              </div>

              {/* Exclude Patterns */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
                  <Filter className="w-4 h-4 text-gray-400" />
                  {t("setup.excludePatterns")}
                </label>
                <textarea
                  value={excludePatterns}
                  onChange={(e) => setExcludePatterns(e.target.value)}
                  onBlur={() => saveSettings({ exclude_patterns: excludePatterns })}
                  placeholder={"/admin/*\n/login\n*.pdf\n/api/*"}
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500 font-mono"
                />
                <p className="text-xs text-gray-400 mt-1">{t("setup.excludePatternsHint")}</p>
              </div>

              {/* Force Recrawl */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceRecrawl}
                  onChange={(e) => setForceRecrawl(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <Zap className="w-4 h-4 text-amber-500" />
                <span className="text-sm text-gray-700">{t("setup.forceRecrawl")}</span>
                <span className="text-xs text-gray-400">{t("setup.forceRecrawlHint")}</span>
              </label>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3 flex-wrap">
            {isRunning ? (
              <>
                <button
                  onClick={() => pauseMutation.mutate()}
                  disabled={pauseMutation.isPending}
                  className="flex items-center gap-2 bg-amber-500 text-white px-4 py-2 rounded-lg hover:bg-amber-600 disabled:opacity-50"
                >
                  <Pause className="w-4 h-4" />
                  {pauseMutation.isPending ? t("setup.pausing") : t("setup.pauseCrawl")}
                </button>
                <button
                  onClick={() => stopMutation.mutate()}
                  disabled={stopMutation.isPending}
                  className="flex items-center gap-2 bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600 disabled:opacity-50"
                >
                  <Square className="w-4 h-4" />
                  {stopMutation.isPending ? t("setup.stopping") : t("setup.stopCrawl")}
                </button>
              </>
            ) : isPaused ? (
              <>
                <button
                  onClick={() => resumeMutation.mutate()}
                  disabled={resumeMutation.isPending}
                  className="flex items-center gap-2 bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 disabled:opacity-50"
                >
                  <SkipForward className="w-4 h-4" />
                  {resumeMutation.isPending ? t("setup.resuming") : t("setup.resumeCrawl")}
                </button>
                <button
                  onClick={() => stopMutation.mutate()}
                  disabled={stopMutation.isPending}
                  className="flex items-center gap-2 bg-red-500 text-white px-4 py-2 rounded-lg hover:bg-red-600 disabled:opacity-50"
                >
                  <Square className="w-4 h-4" />
                  {stopMutation.isPending ? t("setup.stopping") : t("setup.stopCrawl")}
                </button>
              </>
            ) : (
              <button
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending}
                className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                <Play className="w-4 h-4" />
                {startMutation.isPending ? t("setup.starting") : t("setup.startCrawl")}
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
                disabled={clearMutation.isPending || isActive}
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
          <div className="space-y-1">
            {jobs.map((job: { id: string; status: string; pages_done: number; pages_skipped?: number; pages_failed?: number; chunks_created?: number; started_at?: string }) => {
              const isSelected = selectedLogJobId === job.id;
              const isJobActive = job.status === "running" || job.status === "paused";
              return (
                <div key={job.id}>
                  <button
                    onClick={() => {
                      if (isJobActive) return;
                      setSelectedLogJobId(isSelected ? null : job.id);
                      setLogsExpanded(true);
                    }}
                    className={`w-full flex items-center justify-between py-2 px-3 rounded-lg transition-colors ${
                      isSelected
                        ? "bg-gray-100 border border-gray-200"
                        : "hover:bg-gray-50 border border-transparent"
                    } ${isJobActive ? "cursor-default" : "cursor-pointer"}`}
                  >
                    <div className="flex items-center gap-3">
                      {statusIcon(job.status)}
                      <div className="text-left">
                        <span className="text-sm font-medium capitalize">{job.status}</span>
                        <span className="text-xs text-gray-400 ml-2">
                          {job.pages_done} {t("setup.pages")}
                          {job.chunks_created ? ` · ${job.chunks_created} chunks` : ""}
                          {job.pages_failed ? (
                            <span className="text-red-400 ml-1">· {job.pages_failed} {t("setup.failed")}</span>
                          ) : null}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400">
                        {job.started_at ? new Date(job.started_at).toLocaleString() : ""}
                      </span>
                      {!isJobActive && (
                        isSelected
                          ? <ChevronUp className="w-4 h-4 text-gray-400" />
                          : <ChevronDown className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {/* Expanded log view */}
                  {isSelected && logData?.logs?.length > 0 && (
                    <div className="mt-2 mb-3 ml-2">
                      <div className="bg-gray-900 rounded-lg p-4 max-h-80 overflow-y-auto font-mono text-xs">
                        {logData.logs.map((log: LogEntry, i: number) => (
                          <div key={`${log.timestamp}-${log.url || i}`}>
                            {renderLogEntry(log)}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {isSelected && (!logData?.logs || logData.logs.length === 0) && (
                    <div className="mt-2 mb-3 ml-2">
                      <div className="bg-gray-900 rounded-lg p-4 font-mono text-xs text-gray-500 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" />
                        {t("setup.noLogs")}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
