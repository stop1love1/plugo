import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getKnowledge, deleteChunk, addManualChunk, uploadFile } from "../lib/api";
import { Trash2, Plus, Upload, FileText, Search } from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";

const bulkDeleteChunks = (ids: string[]) =>
  api.post("/knowledge/bulk-delete", { chunk_ids: ids }).then((r) => r.data);

export default function Knowledge() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [showAdd, setShowAdd] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);

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

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !siteId) return;
    try {
      await uploadFile(siteId, file);
      queryClient.invalidateQueries({ queryKey: ["knowledge", siteId] });
      toast.success(`File "${file.name}" uploaded`);
    } catch {
      toast.error("Failed to upload file");
    }
  };

  const handleAddManual = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !content || !siteId) return;
    addMutation.mutate({ site_id: siteId, title, content });
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
    <div className="max-w-4xl">
      <PageHeader title="Knowledge Base" subtitle={`${data?.total || 0} chunks`}>
        <label className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 cursor-pointer">
          <Upload className="w-4 h-4" /> Upload File
          <input type="file" accept=".txt,.md" onChange={handleUpload} className="hidden" />
        </label>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> Add Manually
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
          placeholder="Search knowledge..."
          className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 mb-4 p-3 bg-red-50 rounded-lg border border-red-100">
          <span className="text-sm text-red-700">{selectedIds.size} selected</span>
          {showConfirmDelete ? (
            <>
              <span className="text-sm text-red-700 font-medium">Are you sure?</span>
              <button
                onClick={confirmBulkDelete}
                disabled={bulkDeleteMutation.isPending}
                className="text-sm bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 font-medium"
              >
                {bulkDeleteMutation.isPending ? "Deleting..." : "Confirm"}
              </button>
              <button
                onClick={() => setShowConfirmDelete(false)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleBulkDelete}
                disabled={bulkDeleteMutation.isPending}
                className="text-sm text-red-600 hover:text-red-800 font-medium"
              >
                {bulkDeleteMutation.isPending ? "Deleting..." : "Delete Selected"}
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Clear selection
              </button>
            </>
          )}
        </div>
      )}

      {showAdd && (
        <form onSubmit={handleAddManual} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold mb-4">Add New Knowledge</h3>
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
                {addMutation.isPending ? "Saving..." : "Save"}
              </button>
              <button type="button" onClick={() => setShowAdd(false)} className="text-gray-500 px-4 py-2">Cancel</button>
            </div>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : !data?.chunks?.length ? (
        <EmptyState icon={FileText} message={search ? "No results found." : "No data yet. Crawl your website or add content manually."} />
      ) : (
        <div className="space-y-3">
          {data.chunks.map((chunk: any) => (
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
                  <p className="text-sm text-gray-500 mt-1">{chunk.content}</p>
                  <div className="flex gap-3 mt-2 text-xs text-gray-400">
                    <span>{chunk.source_type}</span>
                    {chunk.source_url && <span className="truncate max-w-xs">{chunk.source_url}</span>}
                  </div>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(chunk.id)}
                  className="text-gray-400 hover:text-red-500 p-1 ml-2"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
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
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-gray-500">
                Page {page} / {Math.ceil(data.total / data.per_page)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(data.total / data.per_page)}
                className="px-3 py-1 rounded border text-sm disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
