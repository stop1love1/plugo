import { useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { Users, Trash2, ChevronRight, Brain, ShieldAlert, Search, Filter, ArrowUpDown } from "lucide-react";
import api from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { SkeletonList } from "../components/Skeleton";
import { ConfirmDialog } from "../components/ConfirmDialog";

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

  // Filter and sort visitors
  const filteredVisitors = useMemo(() => {
    let result = visitors;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((v: any) => v.visitor_id.toLowerCase().includes(q));
    }
    if (sortBy === "memories") {
      result = [...result].sort((a: any, b: any) => (b.memory_count || 0) - (a.memory_count || 0));
    }
    return result;
  }, [visitors, searchQuery, sortBy]);

  // Filter memories by category
  const filteredMemories = useMemo(() => {
    if (categoryFilter === "all") return memories;
    return memories.filter((m: any) => m.category === categoryFilter);
  }, [memories, categoryFilter]);

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t("visitors.title")}</h1>
        <p className="text-gray-500 mt-1">{t("visitors.subtitle")}</p>
      </div>

      {isLoading ? (
        <SkeletonList items={4} />
      ) : visitors.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
          <Brain className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">{t("visitors.noMemories")}</p>
        </div>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Visitor list */}
          <div className="w-full lg:w-72 lg:shrink-0">
            {/* Search */}
            <div className="relative mb-3">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("visitors.search")}
                className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* Sort toggle */}
            <div className="flex gap-1 mb-3">
              <button
                onClick={() => setSortBy("memories")}
                className={`flex-1 text-xs px-2 py-1.5 rounded flex items-center justify-center gap-1 ${sortBy === "memories" ? "bg-primary-50 text-primary-700 font-medium" : "text-gray-500 hover:bg-gray-50"}`}
              >
                <ArrowUpDown className="w-3 h-3" />
                {t("visitors.sortMemories")}
              </button>
              <button
                onClick={() => setSortBy("recent")}
                className={`flex-1 text-xs px-2 py-1.5 rounded flex items-center justify-center gap-1 ${sortBy === "recent" ? "bg-primary-50 text-primary-700 font-medium" : "text-gray-500 hover:bg-gray-50"}`}
              >
                {t("visitors.sortRecent")}
              </button>
            </div>

            <div className="space-y-2 max-h-[500px] overflow-y-auto">
              {filteredVisitors.map((v: any) => (
                <button
                  key={v.visitor_id}
                  onClick={() => setSelectedVisitor(v.visitor_id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedVisitor === v.visitor_id
                      ? "border-primary-300 bg-primary-50"
                      : "border-gray-200 bg-white hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700 truncate">
                      {v.visitor_id.substring(0, 12)}...
                    </span>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {v.memory_count} {t("visitors.memories")}
                  </div>
                </button>
              ))}
              {filteredVisitors.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-4">{t("common.noResults")}</p>
              )}
            </div>
          </div>

          {/* Memory details */}
          <div className="flex-1">
            {selectedVisitor ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-700">
                    {t("chatLog.visitor")}: {selectedVisitor.substring(0, 16)}...
                  </h3>
                  <button
                    onClick={() => setShowDeleteAllConfirm(true)}
                    className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
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
                    onConfirm={() => { deleteAllMutation.mutate(); setShowDeleteAllConfirm(false); }}
                    onCancel={() => setShowDeleteAllConfirm(false)}
                  />
                </div>

                {/* Category filter */}
                <div className="flex gap-1 mb-4">
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setCategoryFilter(cat)}
                      className={`text-xs px-2.5 py-1 rounded-full ${
                        categoryFilter === cat
                          ? cat === "all"
                            ? "bg-gray-800 text-white"
                            : (categoryColors[cat] || "bg-gray-100 text-gray-700") + " ring-1 ring-current"
                          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                      }`}
                    >
                      {cat === "all" ? t("visitors.filterAll") : cat}
                    </button>
                  ))}
                </div>

                {filteredMemories.length === 0 ? (
                  <p className="text-sm text-gray-400">{t("common.noResults")}</p>
                ) : (
                  <div className="space-y-2">
                    {filteredMemories.map((mem: any) => (
                      <div key={mem.id} className="bg-white p-3 rounded-lg border border-gray-200">
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`text-xs px-1.5 py-0.5 rounded ${categoryColors[mem.category] || "bg-gray-50 text-gray-600"}`}>
                                {mem.category}
                              </span>
                              <span className="text-xs font-mono text-gray-500">{mem.key}</span>
                              <span className="text-xs text-gray-300">{mem.confidence}</span>
                            </div>
                            <p className="text-sm text-gray-700">{mem.value}</p>
                          </div>
                          <button
                            onClick={() => deleteMemoryMutation.mutate(mem.id)}
                            className="text-gray-300 hover:text-red-500 p-1 ml-2"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-12 text-gray-400 text-sm">
                {t("visitors.selectVisitor")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
