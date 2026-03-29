import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getKnowledge, getChunk, updateChunk, deleteChunk, addManualChunk, uploadFile, bulkDeleteChunks, type KnowledgeChunk } from "../lib/api";
import { Trash2, Plus, Upload, FileText, Search, Pencil, X, ExternalLink, Download } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
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

  // Preview/expand state
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [loadingChunk, setLoadingChunk] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["knowledge", siteId, page, search],
    queryFn: () => getKnowledge(siteId!, page, search || undefined),
    enabled: !!siteId,
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

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { title?: string; content?: string } }) =>
      updateChunk(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      setEditingId(null);
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
    if (!title || !content || !siteId) return;
    addMutation.mutate({ site_id: siteId, title, content });
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
          <Download className="w-4 h-4" /> Export JSON
        </button>
        <label className={`flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer ${uploading ? "opacity-50 pointer-events-none" : ""}`}>
          <Upload className="w-4 h-4" /> {uploading ? t("knowledge.uploading") : t("knowledge.bulkUpload")}
          <input type="file" accept=".txt,.md" multiple onChange={handleUpload} className="hidden" />
        </label>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> {t("knowledge.addManual")}
        </button>
      </PageHeader>

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

      {showAdd && (
        <form onSubmit={handleAddManual} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold mb-4">{t("knowledge.addManual")}</h3>
          <div className="space-y-4">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Content..."
              rows={5}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
            <div className="flex gap-3">
              <button type="submit" disabled={addMutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg">
                {addMutation.isPending ? t("common.loading") : t("common.save")}
              </button>
              <button type="button" onClick={() => setShowAdd(false)} className="text-gray-500 px-4 py-2">{t("common.cancel")}</button>
            </div>
          </div>
        </form>
      )}

      {/* Edit modal */}
      {editingId && (
        <form onSubmit={handleEditSave} className="bg-white p-6 rounded-xl border-2 border-primary-300 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">{t("knowledge.editChunk")}</h3>
            <button type="button" onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-4">
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
              rows={8}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
            />
            <div className="flex gap-3">
              <button type="submit" disabled={updateMutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg">
                {updateMutation.isPending ? t("common.loading") : t("common.save")}
              </button>
              <button type="button" onClick={() => setEditingId(null)} className="text-gray-500 px-4 py-2">{t("common.cancel")}</button>
            </div>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : !data?.chunks?.length ? (
        <EmptyState icon={FileText} message={search ? t("common.noResults") : t("knowledge.noData")} />
      ) : (
        <div className="space-y-3">
          {data.chunks.map((chunk: KnowledgeChunk) => (
            <div key={chunk.id} className={`bg-white p-4 rounded-xl border ${editingId === chunk.id ? "border-primary-300" : "border-gray-200"}`}>
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
                      <p className="text-sm text-gray-500 whitespace-pre-wrap">{chunk.content}</p>
                      <button
                        onClick={() => setExpandedId(null)}
                        className="text-xs text-primary-600 hover:text-primary-700 mt-1"
                      >
                        Show less
                      </button>
                    </div>
                  ) : (
                    <div className="mt-1">
                      <p className="text-sm text-gray-500 line-clamp-2">{chunk.content}</p>
                      {chunk.content && chunk.content.length > 150 && (
                        <button
                          onClick={() => setExpandedId(chunk.id)}
                          className="text-xs text-primary-600 hover:text-primary-700 mt-1"
                        >
                          Read more
                        </button>
                      )}
                    </div>
                  )}
                  <div className="flex gap-3 mt-2 text-xs text-gray-400">
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-gray-100">{chunk.source_type}</span>
                    {chunk.source_url && (
                      <a href={chunk.source_url} target="_blank" rel="noopener noreferrer"
                        className="truncate max-w-xs hover:text-primary-600 inline-flex items-center gap-1">
                        {chunk.source_url}
                        <ExternalLink className="w-3 h-3" />
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
                    onClick={() => deleteMutation.mutate(chunk.id)}
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
