import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getKnowledge, getChunk, updateChunk, deleteChunk, addManualChunk, uploadFile, bulkDeleteChunks, getCrawlSiteStatus, getSiteCrawlJobs, clearAllKnowledge, type KnowledgeChunk } from "../lib/api";
import { Trash2, Plus, Upload, FileText, Search, Pencil, X, ExternalLink, Download, RefreshCw, Link as LinkIcon, AlertTriangle } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useLocale } from "../lib/useLocale";

export default function Knowledge() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [page, setPage] = useState(1);
  const [showAdd, setShowAdd] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);
  const [showClearAll, setShowClearAll] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // Preview/expand state (list API truncates content >200 chars; fetch full on expand)
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedFetchedContent, setExpandedFetchedContent] = useState<string | null>(null);
  const [loadingExpandId, setLoadingExpandId] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [loadingChunk, setLoadingChunk] = useState(false);

  function closeEditModal() {
    setEditingId(null);
    setEditTitle("");
    setEditContent("");
  }

  // Crawl status for progress bar
  const { data: crawlStatus } = useQuery({
    queryKey: ["crawl-status-knowledge", siteId],
    queryFn: () => getCrawlSiteStatus(siteId!),
    enabled: !!siteId,
    refetchInterval: (query) => {
      const s = query.state.data;
      return s?.is_running || s?.is_paused ? 2000 : false;
    },
  });
  const { data: crawlJobs } = useQuery({
    queryKey: ["crawl-jobs-knowledge", siteId],
    queryFn: () => getSiteCrawlJobs(siteId!),
    enabled: !!siteId && (crawlStatus?.is_running || crawlStatus?.is_paused || false),
    refetchInterval: 3000,
  });
  const activeJob = crawlJobs?.find((j) => j.status === "running" || j.status === "paused");
  const isCrawling = crawlStatus?.is_running || false;

  const { data, isLoading } = useQuery({
    queryKey: ["knowledge", siteId, page, search],
    queryFn: () => getKnowledge(siteId!, page, search || undefined),
    enabled: !!siteId,
    refetchInterval: isCrawling ? 5000 : false,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteChunk,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      toast.success("Chunk deleted");
    },
    onError: () => toast.error("Failed to delete chunk"),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => bulkDeleteChunks(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      setSelectedIds(new Set());
      toast.success(`${data.deleted} chunks deleted`);
    },
    onError: () => toast.error("Failed to delete chunks"),
  });

  const addMutation = useMutation({
    mutationFn: addManualChunk,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      setShowAdd(false);
      setTitle("");
      setContent("");
      toast.success("Knowledge added");
    },
    onError: () => toast.error("Failed to add knowledge"),
  });

  const clearAllMutation = useMutation({
    mutationFn: () => clearAllKnowledge(siteId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      queryClient.invalidateQueries({ queryKey: ["crawl-status-knowledge", siteId] });
      setShowClearAll(false);
      toast.success(t("knowledge.allCleared"));
    },
    onError: () => toast.error("Failed to clear knowledge"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { title?: string; content?: string } }) =>
      updateChunk(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      closeEditModal();
      toast.success(t("knowledge.updateSuccess"));
    },
    onError: () => toast.error(t("knowledge.updateFailed")),
  });

  const [uploading, setUploading] = useState(false);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || !siteId) return;
    setUploading(true);
    let successCount = 0;
    let failCount = 0;
    for (const file of Array.from(files)) {
      try {
        await uploadFile(siteId, file);
        successCount++;
      } catch {
        failCount++;
      }
    }
    queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
    setUploading(false);
    if (successCount > 0) toast.success(`${successCount} file(s) uploaded`);
    if (failCount > 0) toast.error(`${failCount} file(s) failed`);
    // Reset input
    e.target.value = "";
  };

  const handleAddManual = (e: React.FormEvent) => {
    e.preventDefault();
    if (!content || !siteId) return;
    // Auto-generate title from first line of content if not provided
    const autoTitle = title.trim() || content.trim().split("\n")[0].slice(0, 100) || "Manual entry";
    addMutation.mutate({ site_id: siteId, title: autoTitle, content });
  };

  const startEdit = async (chunkId: string) => {
    setLoadingChunk(true);
    try {
      const fullChunk = await getChunk(chunkId);
      setEditingId(chunkId);
      setEditTitle(fullChunk.title || "");
      setEditContent(fullChunk.content || "");
    } catch {
      toast.error("Failed to load chunk");
    }
    setLoadingChunk(false);
  };

  const handleEditSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingId || !editTitle || !editContent) return;
    updateMutation.mutate({ id: editingId, data: { title: editTitle, content: editContent } });
  };

  /** List API returns first 200 chars + "..." when content length > 200. */
  const isApiTruncatedListContent = (content: string) => content.endsWith("...") && content.length >= 203;

  const handleReadMore = async (chunk: KnowledgeChunk) => {
    if (isApiTruncatedListContent(chunk.content)) {
      setLoadingExpandId(chunk.id);
      try {
        const full = await getChunk(chunk.id);
        setExpandedId(chunk.id);
        setExpandedFetchedContent(full.content ?? "");
      } catch {
        toast.error(t("knowledge.loadChunkFailed"));
      }
      setLoadingExpandId(null);
    } else {
      setExpandedId(chunk.id);
      setExpandedFetchedContent(null);
    }
  };

  const handleShowLess = () => {
    setExpandedId(null);
    setExpandedFetchedContent(null);
  };

  const exportAllJson = () => {
    if (!data?.chunks?.length) return;
    const json = JSON.stringify(data.chunks, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `knowledge-${siteId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return;
    setShowConfirmDelete(true);
  };

  const confirmBulkDelete = () => {
    bulkDeleteMutation.mutate(Array.from(selectedIds));
    setShowConfirmDelete(false);
  };

  return (
    <div>
      <PageHeader title={t("knowledge.title")} subtitle={`${data?.total || 0} ${t("knowledge.chunks")}`}>
        <button
          onClick={exportAllJson}
          disabled={!data?.chunks?.length}
          className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          <Download className="w-4 h-4" /> Export Page (JSON)
        </button>
        <label className={`flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer ${uploading ? "opacity-50 pointer-events-none" : ""}`}>
          <Upload className="w-4 h-4" /> {uploading ? t("knowledge.uploading") : t("knowledge.bulkUpload")}
          <input type="file" accept=".txt,.md,.pdf,.docx,.csv" multiple onChange={handleUpload} className="hidden" />
        </label>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> {t("knowledge.addManual")}
        </button>
        <button
          onClick={() => setShowClearAll(true)}
          disabled={!data?.total}
          className="flex items-center gap-2 bg-white border border-red-300 text-red-600 px-4 py-2 rounded-lg hover:bg-red-50 disabled:opacity-50"
        >
          <Trash2 className="w-4 h-4" /> {t("knowledge.clearAll")}
        </button>
      </PageHeader>

      {/* Crawl progress bar */}
      {isCrawling && activeJob && (
        <div className="mb-4 p-4 bg-blue-50 rounded-xl border border-blue-100">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-sm font-medium text-blue-800">
              {t("knowledge.crawlInProgress")}
            </span>
            <span className="text-xs text-blue-500 ml-auto">
              {activeJob.pages_done}/{crawlStatus?.crawl_max_pages || 50} {t("setup.pages")}
              {activeJob.chunks_created > 0 && ` · ${activeJob.chunks_created} chunks`}
            </span>
          </div>
          {/* Progress bar */}
          <div className="w-full bg-blue-200 rounded-full h-2 mb-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, ((activeJob.pages_done || 0) / (crawlStatus?.crawl_max_pages || 50)) * 100)}%` }}
            />
          </div>
          {/* Current URL */}
          {crawlStatus?.current_url && (
            <div className="flex items-center gap-1.5">
              <LinkIcon className="w-3 h-3 text-blue-400 shrink-0" />
              <span className="text-xs text-blue-600 truncate" title={crawlStatus.current_url}>
                {crawlStatus.current_url}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Search bar */}
      <div className="relative mb-4">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder={t("knowledge.searchKnowledge")}
          className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 mb-4 p-3 bg-red-50 rounded-lg border border-red-100">
          <span className="text-sm text-red-700">{selectedIds.size} {t("common.selected")}</span>
          {showConfirmDelete ? (
            <>
              <span className="text-sm text-red-700 font-medium">{t("knowledge.confirmDelete")}</span>
              <button
                onClick={confirmBulkDelete}
                disabled={bulkDeleteMutation.isPending}
                className="text-sm bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 font-medium"
              >
                {bulkDeleteMutation.isPending ? t("common.loading") : t("common.confirm")}
              </button>
              <button
                onClick={() => setShowConfirmDelete(false)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                {t("common.cancel")}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleBulkDelete}
                disabled={bulkDeleteMutation.isPending}
                className="text-sm text-red-600 hover:text-red-800 font-medium"
              >
                {bulkDeleteMutation.isPending ? t("common.loading") : t("common.deleteSelected")}
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                {t("common.clearSelection")}
              </button>
            </>
          )}
        </div>
      )}

      {/* Add Manual Modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="fixed inset-0 bg-black/40" onClick={() => setShowAdd(false)} />
          <form onSubmit={handleAddManual} className="relative bg-white rounded-xl shadow-xl w-full max-w-lg p-6 z-10">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg">{t("knowledge.addManual")}</h3>
              <button type="button" onClick={() => setShowAdd(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t("knowledge.chunkTitle")} <span className="text-gray-400 font-normal">({t("common.optional")})</span>
                </label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t("knowledge.titlePlaceholder")}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                />
                <p className="text-xs text-gray-400 mt-1">{t("knowledge.titleAutoHint")}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {t("knowledge.content")} <span className="text-red-400">*</span>
                </label>
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={t("knowledge.contentPlaceholder")}
                  rows={8}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => setShowAdd(false)} className="text-gray-500 px-4 py-2 hover:bg-gray-100 rounded-lg">
                  {t("common.cancel")}
                </button>
                <button type="submit" disabled={addMutation.isPending || !content.trim()} className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {addMutation.isPending ? t("common.loading") : t("common.save")}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Clear All Confirmation Modal */}
      {showClearAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="fixed inset-0 bg-black/40" onClick={() => setShowClearAll(false)} />
          <div className="relative bg-white rounded-xl shadow-xl w-full max-w-sm p-6 z-10">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-500" />
              <h3 className="font-semibold text-lg">{t("knowledge.clearAll")}</h3>
            </div>
            <p className="text-sm text-gray-600 mb-6">{t("knowledge.clearAllConfirm")}</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowClearAll(false)} className="text-gray-500 px-4 py-2 hover:bg-gray-100 rounded-lg">
                {t("common.cancel")}
              </button>
              <button
                onClick={() => clearAllMutation.mutate()}
                disabled={clearAllMutation.isPending}
                className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {clearAllMutation.isPending ? t("common.loading") : t("knowledge.confirmClear")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="knowledge-edit-title">
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => {
              if (!updateMutation.isPending) closeEditModal();
            }}
          />
          <form
            onSubmit={handleEditSave}
            className="relative bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col p-6 z-10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4 shrink-0">
              <h3 id="knowledge-edit-title" className="font-semibold text-gray-900">
                {t("knowledge.editChunk")}
              </h3>
              <button
                type="button"
                onClick={() => {
                  if (!updateMutation.isPending) closeEditModal();
                }}
                className="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-gray-100"
                aria-label={t("common.cancel")}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4 overflow-y-auto min-h-0 flex-1">
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder="Title"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
              />
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                placeholder="Content..."
                rows={10}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 min-h-[200px]"
              />
            </div>
            <div className="flex gap-3 mt-4 pt-4 border-t border-gray-100 shrink-0">
              <button type="submit" disabled={updateMutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg disabled:opacity-50">
                {updateMutation.isPending ? t("common.loading") : t("common.save")}
              </button>
              <button
                type="button"
                disabled={updateMutation.isPending}
                onClick={closeEditModal}
                className="text-gray-600 px-4 py-2 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Single-item delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={t("common.delete")}
        message={t("knowledge.confirmDelete")}
        confirmLabel={t("common.delete")}
        danger
        loading={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget, {
              onSettled: () => setDeleteTarget(null),
            });
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : !data?.chunks?.length ? (
        <EmptyState icon={FileText} message={search ? t("common.noResults") : t("knowledge.noData")} />
      ) : (
        <div className="space-y-3">
          {data.chunks.map((chunk: KnowledgeChunk) => (
            <div key={chunk.id} className="bg-white p-4 rounded-xl border border-gray-200">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={selectedIds.has(chunk.id)}
                  onChange={() => toggleSelect(chunk.id)}
                  className="mt-1 rounded border-gray-300"
                />
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-gray-900 truncate">{chunk.title || "Untitled"}</h4>
                  {expandedId === chunk.id ? (
                    <div className="mt-1">
                      <p className="text-sm text-gray-500 whitespace-pre-wrap break-words">
                        {expandedFetchedContent ?? chunk.content}
                      </p>
                      <button
                        type="button"
                        onClick={handleShowLess}
                        className="text-xs text-primary-600 hover:text-primary-700 mt-1"
                      >
                        {t("knowledge.showLess")}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-1 relative z-0">
                      <p className="text-sm text-gray-500 line-clamp-2 break-words">{chunk.content}</p>
                      {chunk.content &&
                        (chunk.content.length > 150 || isApiTruncatedListContent(chunk.content)) && (
                          <button
                            type="button"
                            onClick={() => handleReadMore(chunk)}
                            disabled={loadingExpandId === chunk.id}
                            className="text-xs text-primary-600 hover:text-primary-700 mt-1 disabled:opacity-50"
                          >
                            {loadingExpandId === chunk.id ? t("common.loading") : t("knowledge.viewFull")}
                          </button>
                        )}
                    </div>
                  )}
                  <div className="mt-2 flex flex-wrap items-start gap-x-3 gap-y-1 text-xs text-gray-400">
                    <span className="inline-flex shrink-0 items-center px-1.5 py-0.5 rounded bg-gray-100">
                      {chunk.source_type}
                    </span>
                    {chunk.source_url && (
                      <a
                        href={chunk.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex min-w-0 flex-1 items-start gap-1.5 text-primary-600 hover:text-primary-700 break-all [overflow-wrap:anywhere]"
                      >
                        <ExternalLink className="w-3 h-3 shrink-0 mt-0.5 opacity-80" aria-hidden />
                        <span>{chunk.source_url}</span>
                      </a>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 ml-2">
                  <button
                    onClick={() => startEdit(chunk.id)}
                    disabled={loadingChunk}
                    className="text-gray-400 hover:text-primary-600 p-1"
                    title={t("common.edit")}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setDeleteTarget(chunk.id)}
                    className="text-gray-400 hover:text-red-500 p-1"
                    title={t("common.delete")}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}

          {/* Pagination */}
          {data.total > data.per_page && (
            <div className="flex justify-center gap-2 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded border text-sm disabled:opacity-50"
              >
                {t("common.previous")}
              </button>
              <span className="px-3 py-1 text-sm text-gray-500">
                {t("common.page")} {page} / {Math.ceil(data.total / data.per_page)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / data.per_page)}
                className="px-3 py-1 rounded border text-sm disabled:opacity-50"
              >
                {t("common.next")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
