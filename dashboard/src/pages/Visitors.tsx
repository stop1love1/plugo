import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { Users, Trash2, ChevronRight, Brain, ShieldAlert } from "lucide-react";
import api from "../lib/api";

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

export default function Visitors() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const [selectedVisitor, setSelectedVisitor] = useState<string | null>(null);

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

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Visitor Memory</h1>
        <p className="text-gray-500 mt-1">View and manage what the bot remembers about visitors</p>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : visitors.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
          <Brain className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No visitor memories yet. Memories are extracted automatically after chat sessions.</p>
        </div>
      ) : (
        <div className="flex gap-6">
          {/* Visitor list */}
          <div className="w-72 shrink-0 space-y-2">
            {visitors.map((v: any) => (
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
                  {v.memory_count} memories
                </div>
              </button>
            ))}
          </div>

          {/* Memory details */}
          <div className="flex-1">
            {selectedVisitor ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-700">
                    Visitor: {selectedVisitor.substring(0, 16)}...
                  </h3>
                  <button
                    onClick={() => {
                      if (confirm("Delete ALL memories for this visitor? This cannot be undone.")) {
                        deleteAllMutation.mutate();
                      }
                    }}
                    className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
                  >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Delete All (GDPR)
                  </button>
                </div>

                {memories.length === 0 ? (
                  <p className="text-sm text-gray-400">No memories for this visitor.</p>
                ) : (
                  <div className="space-y-2">
                    {memories.map((mem: any) => (
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
                Select a visitor to view their memories
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
