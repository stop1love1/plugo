import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getCrawledUrls, getChunksByUrl, deleteByUrl, recrawlUrl,
  type CrawledUrl, type KnowledgeChunk,
} from "../lib/api";
import {
  Globe, Trash2, RefreshCw, ChevronDown, ChevronUp,
  ExternalLink, Search, AlertTriangle,
} from "lucide-react";
import { useLocale } from "../lib/useLocale";

export default function CrawledPages() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [search, setSearch] = useState("");
  const [expandedUrl, setExpandedUrl] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const { data: urls = [], isLoading } = useQuery({
    queryKey: ["crawled-urls", siteId],
    queryFn: () => getCrawledUrls(siteId!),
    enabled: !!siteId,
  });

  const { data: chunkData } = useQuery({
    queryKey: ["url-chunks", siteId, expandedUrl],
    queryFn: () => getChunksByUrl(siteId!, expandedUrl!),
    enabled: !!siteId && !!expandedUrl,
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceUrl: string) => deleteByUrl(siteId!, sourceUrl),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["crawled-urls", siteId] });
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      setConfirmDelete(null);
      setExpandedUrl(null);
      toast.success(`${data.deleted} chunks deleted`);
    },
    onError: () => toast.error(t("crawledPages.deleteFailed")),
  });

  const recrawlMutation = useMutation({
    mutationFn: (sourceUrl: string) => recrawlUrl(siteId!, sourceUrl),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["crawled-urls", siteId] });
      queryClient.invalidateQueries({ queryKey: ["url-chunks", siteId] });
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      toast.success(`${data.new_chunks} chunks updated`);
    },
    onError: () => toast.error(t("crawledPages.recrawlFailed")),
  });

  const filtered = search
    ? urls.filter((u: CrawledUrl) =>
        u.source_url.toLowerCase().includes(search.toLowerCase()) ||
        (u.title || "").toLowerCase().includes(search.toLowerCase())
      )
    : urls;

  const totalChunks = urls.reduce((sum: number, u: CrawledUrl) => sum + u.chunk_count, 0);

  const sourceTypeLabel = (type: string) => {
    switch (type) {
      case "crawl": return t("crawledPages.typeCrawl");
      case "manual": return t("crawledPages.typeManual");
      case "upload": return t("crawledPages.typeUpload");
      default: return type;
    }
  };

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("crawledPages.title")}</h1>
        <div className="text-gray-400 mt-8">{t("common.loading")}</div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("crawledPages.title")}</h1>
          <p className="text-gray-500">{t("crawledPages.subtitle")}</p>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white p-4 rounded-xl border border-gray-200 text-center">
          <div className="text-2xl font-bold text-primary-600">{urls.length}</div>
          <div className="text-xs text-gray-500">{t("crawledPages.totalUrls")}</div>
        </div>
        <div className="bg-white p-4 rounded-xl border border-gray-200 text-center">
          <div className="text-2xl font-bold text-primary-600">{totalChunks}</div>
          <div className="text-xs text-gray-500">{t("crawledPages.totalChunks")}</div>
        </div>
        <div className="bg-white p-4 rounded-xl border border-gray-200 text-center">
          <div className="text-2xl font-bold text-gray-600">
            {urls.length > 0 ? (totalChunks / urls.length).toFixed(1) : "0"}
          </div>
          <div className="text-xs text-gray-500">{t("crawledPages.avgChunks")}</div>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("crawledPages.searchPlaceholder")}
          className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* URL List */}
      {filtered.length === 0 ? (
        <div className="bg-white p-8 rounded-xl border border-gray-200 text-center">
          <Globe className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">
            {search ? t("crawledPages.noResults") : t("crawledPages.empty")}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((url: CrawledUrl) => {
            const isExpanded = expandedUrl === url.source_url;
            const isDeleting = confirmDelete === url.source_url;

            return (
              <div key={url.source_url} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                {/* URL header row */}
                <button
                  onClick={() => setExpandedUrl(isExpanded ? null : url.source_url)}
                  className="w-full flex items-center gap-3 p-4 hover:bg-gray-50 transition-colors text-left"
                >
                  <Globe className="w-4 h-4 text-gray-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900 truncate">
                        {url.title || url.source_url}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        url.source_type === "crawl" ? "bg-blue-50 text-blue-600" :
                        url.source_type === "manual" ? "bg-green-50 text-green-600" :
                        "bg-purple-50 text-purple-600"
                      }`}>
                        {sourceTypeLabel(url.source_type)}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 truncate mt-0.5">{url.source_url}</div>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <div className="text-right">
                      <div className="text-sm font-medium text-primary-600">{url.chunk_count}</div>
                      <div className="text-[10px] text-gray-400">chunks</div>
                    </div>
                    {url.last_crawled_at && (
                      <div className="text-right hidden sm:block">
                        <div className="text-xs text-gray-500">
                          {new Date(url.last_crawled_at).toLocaleDateString()}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {new Date(url.last_crawled_at).toLocaleTimeString()}
                        </div>
                      </div>
                    )}
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                  </div>
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-gray-100">
                    {/* Actions bar */}
                    <div className="flex items-center gap-2 px-4 py-3 bg-gray-50">
                      <a
                        href={url.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 px-2 py-1 rounded border border-primary-200 bg-white"
                      >
                        <ExternalLink className="w-3 h-3" />
                        {t("crawledPages.openUrl")}
                      </a>
                      <button
                        onClick={() => recrawlMutation.mutate(url.source_url)}
                        disabled={recrawlMutation.isPending}
                        className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 px-2 py-1 rounded border border-blue-200 bg-white disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3 h-3 ${recrawlMutation.isPending ? "animate-spin" : ""}`} />
                        {recrawlMutation.isPending ? t("crawledPages.recrawling") : t("crawledPages.recrawl")}
                      </button>
                      {isDeleting ? (
                        <div className="flex items-center gap-2 ml-auto">
                          <span className="text-xs text-red-600">{t("crawledPages.confirmDelete")}</span>
                          <button
                            onClick={() => deleteMutation.mutate(url.source_url)}
                            disabled={deleteMutation.isPending}
                            className="text-xs bg-red-600 text-white px-2 py-1 rounded hover:bg-red-700 disabled:opacity-50"
                          >
                            {t("common.confirm")}
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="text-xs text-gray-500 hover:text-gray-700"
                          >
                            {t("common.cancel")}
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(url.source_url)}
                          className="flex items-center gap-1 text-xs text-red-500 hover:text-red-600 px-2 py-1 rounded border border-red-200 bg-white ml-auto"
                        >
                          <Trash2 className="w-3 h-3" />
                          {t("crawledPages.deleteUrl")}
                        </button>
                      )}
                    </div>

                    {/* Chunks list */}
                    <div className="px-4 py-3">
                      {!chunkData?.chunks ? (
                        <div className="text-xs text-gray-400">{t("common.loading")}</div>
                      ) : chunkData.chunks.length === 0 ? (
                        <div className="text-xs text-gray-400 flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4" />
                          {t("crawledPages.noChunks")}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-gray-500 mb-2">
                            {chunkData.chunks.length} {t("crawledPages.chunksInPage")}
                          </div>
                          {chunkData.chunks.map((chunk: KnowledgeChunk, i: number) => (
                            <div key={chunk.id} className="border border-gray-100 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[10px] font-medium text-gray-400">
                                  #{i + 1} · {chunk.title || t("crawledPages.untitled")}
                                </span>
                                <span className="text-[10px] text-gray-300">
                                  {chunk.content.length} chars
                                </span>
                              </div>
                              <p className="text-xs text-gray-600 line-clamp-3 whitespace-pre-wrap">
                                {chunk.content.substring(0, 300)}{chunk.content.length > 300 ? "..." : ""}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
