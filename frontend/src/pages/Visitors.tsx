import { useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { Users, Trash2, ChevronRight, Brain, ShieldAlert, Search, ArrowUpDown } from "lucide-react";
import api from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { SkeletonList } from "../components/Skeleton";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";

const getVisitors = (siteId: string) =>
  api.get(`/memory/visitors?site_id=${siteId}`).then((r) => r.data);
const getVisitorMemories = (visitorId: string, siteId: string) =>
  api.get(`/memory/visitor/${visitorId}?site_id=${siteId}`).then((r) => r.data);
const deleteMemory = (id: string) =>
  api.delete(`/memory/${id}`).then((r) => r.data);
const deleteVisitorMemories = (visitorId: string, siteId: string) =>
  api.delete(`/memory/visitor/${visitorId}?site_id=${siteId}`).then((r) => r.data);

const categoryColors: Record<string, string> = {
  identity: "bg-blue-50 text-blue-700",
  preference: "bg-purple-50 text-purple-700",
  issue: "bg-red-50 text-red-700",
  context: "bg-green-50 text-green-700",
};

const categories = ["all", "identity", "preference", "issue", "context"];

export default function Visitors() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [selectedVisitor, setSelectedVisitor] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [sortBy, setSortBy] = useState<"memories" | "recent">("memories");
  const [showDeleteAllConfirm, setShowDeleteAllConfirm] = useState(false);

  const { data: visitors = [], isLoading } = useQuery({
    queryKey: ["visitors", siteId],
    queryFn: () => getVisitors(siteId!),
    enabled: !!siteId,
  });

  const { data: memories = [] } = useQuery({
    queryKey: ["visitor-memories", selectedVisitor, siteId],
    queryFn: () => getVisitorMemories(selectedVisitor!, siteId!),
    enabled: !!selectedVisitor && !!siteId,
  });

  const deleteMemoryMutation = useMutation({
    mutationFn: deleteMemory,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["visitor-memories", selectedVisitor, siteId] });
      queryClient.invalidateQueries({ queryKey: ["visitors", siteId] });
      toast.success("Memory deleted");
    },
    onError: () => toast.error("Failed to delete memory"),
  });

  const deleteAllMutation = useMutation({
    mutationFn: () => deleteVisitorMemories(selectedVisitor!, siteId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["visitors", siteId] });
      setSelectedVisitor(null);
      toast.success("All visitor memories deleted");
    },
    onError: () => toast.error("Failed to delete memories"),
  });

  const filteredVisitors = useMemo(() => {
    let result = visitors;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((v: { visitor_id: string }) => v.visitor_id.toLowerCase().includes(q));
    }
    if (sortBy === "memories") {
      result = [...result].sort(
        (a: { memory_count?: number }, b: { memory_count?: number }) =>
          (b.memory_count || 0) - (a.memory_count || 0)
      );
    } else {
      result = [...result].sort((a: { last_updated?: string }, b: { last_updated?: string }) => {
        const ta = new Date(a.last_updated || 0).getTime();
        const tb = new Date(b.last_updated || 0).getTime();
        return tb - ta;
      });
    }
    return result;
  }, [visitors, searchQuery, sortBy]);

  const filteredMemories = useMemo(() => {
    if (categoryFilter === "all") return memories;
    return memories.filter((m: { category: string }) => m.category === categoryFilter);
  }, [memories, categoryFilter]);

  return (
    <div className="flex flex-col h-[calc(100dvh-7rem)] min-h-[28rem] lg:h-[calc(100dvh-5.5rem)] lg:min-h-[32rem]">
      <PageHeader title={t("visitors.title")} subtitle={t("visitors.subtitle")} className="mb-4 shrink-0" />

      {isLoading ? (
        <div className="flex-1 min-h-0">
          <SkeletonList items={4} />
        </div>
      ) : visitors.length === 0 ? (
        <div className="flex-1 min-h-0 flex flex-col">
          <EmptyState icon={Brain} message={t("visitors.noMemories")} />
        </div>
      ) : (
        <div className="flex flex-col lg:flex-row flex-1 min-h-0 gap-0 lg:gap-0 border border-gray-200 rounded-xl bg-white overflow-hidden shadow-sm">
          <aside className="flex flex-col min-h-0 w-full lg:w-80 lg:shrink-0 border-b lg:border-b-0 lg:border-r border-gray-200 bg-gray-50/50">
            <div className="p-3 space-y-3 shrink-0 border-b border-gray-100 bg-white/80">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("visitors.search")}
                  className="w-full border border-gray-200 rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                />
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => setSortBy("memories")}
                  className={`flex-1 text-xs px-2 py-1.5 rounded-md flex items-center justify-center gap-1 transition-colors ${
                    sortBy === "memories"
                      ? "bg-primary-600 text-white shadow-sm"
                      : "text-gray-600 hover:bg-gray-100 bg-white border border-gray-200"
                  }`}
                >
                  <ArrowUpDown className="w-3 h-3" />
                  {t("visitors.sortMemories")}
                </button>
                <button
                  type="button"
                  onClick={() => setSortBy("recent")}
                  className={`flex-1 text-xs px-2 py-1.5 rounded-md transition-colors ${
                    sortBy === "recent"
                      ? "bg-primary-600 text-white shadow-sm"
                      : "text-gray-600 hover:bg-gray-100 bg-white border border-gray-200"
                  }`}
                >
                  {t("visitors.sortRecent")}
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1.5">
              {filteredVisitors.map((v: { visitor_id: string; memory_count?: number }) => (
                <button
                  key={v.visitor_id}
                  type="button"
                  onClick={() => setSelectedVisitor(v.visitor_id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedVisitor === v.visitor_id
                      ? "border-primary-400 bg-primary-50 ring-1 ring-primary-200"
                      : "border-transparent bg-white hover:border-gray-200 hover:bg-white shadow-sm"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-gray-800 truncate font-mono">
                      {v.visitor_id.substring(0, 14)}…
                    </span>
                    <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                  </div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {v.memory_count} {t("visitors.memories")}
                  </div>
                </button>
              ))}
              {filteredVisitors.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-6">{t("common.noResults")}</p>
              )}
            </div>
          </aside>

          <section className="flex flex-col flex-1 min-h-0 min-w-0 bg-white">
            {selectedVisitor ? (
              <>
                <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50/40">
                  <h3 className="font-semibold text-gray-800 text-sm sm:text-base truncate max-w-[min(100%,28rem)] font-mono">
                    {t("chatLog.visitor")}: {selectedVisitor}
                  </h3>
                  <button
                    type="button"
                    onClick={() => setShowDeleteAllConfirm(true)}
                    className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800 font-medium px-2 py-1 rounded-md hover:bg-red-50"
                  >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    {t("visitors.deleteAll")}
                  </button>
                  <ConfirmDialog
                    open={showDeleteAllConfirm}
                    title={t("visitors.deleteAll")}
                    message="Delete ALL memories for this visitor? This cannot be undone."
                    danger
                    loading={deleteAllMutation.isPending}
                    onConfirm={() => {
                      deleteAllMutation.mutate();
                      setShowDeleteAllConfirm(false);
                    }}
                    onCancel={() => setShowDeleteAllConfirm(false)}
                  />
                </div>

                <div className="shrink-0 px-4 py-2 border-b border-gray-100 flex flex-wrap gap-1.5">
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setCategoryFilter(cat)}
                      className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                        categoryFilter === cat
                          ? cat === "all"
                            ? "bg-gray-800 text-white"
                            : `${categoryColors[cat] || "bg-gray-100 text-gray-700"} ring-1 ring-current`
                          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                      }`}
                    >
                      {cat === "all" ? t("visitors.filterAll") : cat}
                    </button>
                  ))}
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-4">
                  {filteredMemories.length === 0 ? (
                    <p className="text-sm text-gray-400 py-8 text-center">{t("common.noResults")}</p>
                  ) : (
                    <div className="space-y-2 max-w-4xl">
                      {filteredMemories.map((mem: { id: string; category: string; key: string; confidence?: string; value: string }) => (
                        <div key={mem.id} className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span
                                  className={`text-xs px-1.5 py-0.5 rounded ${categoryColors[mem.category] || "bg-gray-50 text-gray-600"}`}
                                >
                                  {mem.category}
                                </span>
                                <span className="text-xs font-mono text-gray-500">{mem.key}</span>
                                {mem.confidence != null && (
                                  <span className="text-xs text-gray-300">{mem.confidence}</span>
                                )}
                              </div>
                              <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">{mem.value}</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => deleteMemoryMutation.mutate(mem.id)}
                              className="text-gray-300 hover:text-red-500 p-1.5 rounded-md hover:bg-red-50 shrink-0"
                              aria-label={t("common.delete")}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 min-h-0 flex items-center justify-center text-gray-400 text-sm px-6 text-center">
                {t("visitors.selectVisitor")}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
