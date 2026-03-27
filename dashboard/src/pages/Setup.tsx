import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getSite, startCrawl, getCrawlStatus, getSiteCrawlJobs } from "../lib/api";
import { Globe, Play, RefreshCw, CheckCircle, XCircle, Clock } from "lucide-react";

export default function Setup() {
  const { siteId } = useParams<{ siteId: string }>();
  const [crawlUrl, setCrawlUrl] = useState("");
  const [maxPages, setMaxPages] = useState(50);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: jobs = [], refetch: refetchJobs } = useQuery({
    queryKey: ["crawl-jobs", siteId],
    queryFn: () => getSiteCrawlJobs(siteId!),
    enabled: !!siteId,
    refetchInterval: activeJobId ? 3000 : false,
  });

  const { data: activeJob } = useQuery({
    queryKey: ["crawl-job", activeJobId],
    queryFn: () => getCrawlStatus(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: 2000,
  });

  const crawlMutation = useMutation({
    mutationFn: startCrawl,
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
      refetchJobs();
    },
  });

  const handleStartCrawl = () => {
    if (!siteId) return;
    const url = crawlUrl || site?.url;
    if (!url) return;
    crawlMutation.mutate({ site_id: siteId, url, max_pages: maxPages });
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "failed": return <XCircle className="w-4 h-4 text-red-500" />;
      case "running": return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Crawl & Setup</h1>
      <p className="text-gray-500 mb-8">Cho Plugo học nội dung website của bạn</p>

      {/* Crawl form */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5" /> Crawl Website
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL bắt đầu</label>
            <input
              value={crawlUrl}
              onChange={(e) => setCrawlUrl(e.target.value)}
              placeholder={site?.url || "https://example.com"}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Số trang tối đa</label>
            <input
              type="number"
              value={maxPages}
              onChange={(e) => setMaxPages(parseInt(e.target.value) || 50)}
              min={1}
              max={500}
              className="w-32 border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <button
            onClick={handleStartCrawl}
            disabled={crawlMutation.isPending}
            className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {crawlMutation.isPending ? "Đang bắt đầu..." : "Bắt đầu Crawl"}
          </button>
        </div>
      </div>

      {/* Active crawl progress */}
      {activeJob && activeJob.status === "running" && (
        <div className="bg-blue-50 border border-blue-200 p-4 rounded-xl mb-6">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="w-4 h-4 text-blue-600 animate-spin" />
            <span className="font-medium text-blue-800">Đang crawl...</span>
          </div>
          <div className="text-sm text-blue-700">
            Đã xử lý {activeJob.pages_done} / {activeJob.pages_found} trang
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2 mt-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all"
              style={{ width: `${activeJob.pages_found ? (activeJob.pages_done / activeJob.pages_found) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Crawl history */}
      {jobs.length > 0 && (
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">Lịch sử Crawl</h3>
          <div className="space-y-3">
            {jobs.map((job: any) => (
              <div key={job.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <div className="flex items-center gap-3">
                  {statusIcon(job.status)}
                  <div>
                    <span className="text-sm font-medium capitalize">{job.status}</span>
                    <span className="text-xs text-gray-400 ml-2">
                      {job.pages_done} trang
                    </span>
                  </div>
                </div>
                <span className="text-xs text-gray-400">
                  {job.started_at ? new Date(job.started_at).toLocaleString("vi-VN") : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
