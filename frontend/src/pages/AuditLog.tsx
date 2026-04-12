import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuditLogs, type AuditLogEntry } from "../lib/api";
import { FileText, Search, Info } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { useLocale } from "../lib/useLocale";

const actionColors: Record<string, string> = {
  create: "bg-green-50 text-green-700",
  update: "bg-blue-50 text-blue-700",
  delete: "bg-red-50 text-red-700",
};

export default function AuditLog() {
  const { t } = useLocale();
  const [page, setPage] = useState(1);
  const [searchFilter, setSearchFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("all");

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [searchFilter, actionFilter]);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", page],
    queryFn: () => getAuditLogs(page),
  });

  const filteredLogs = useMemo(() => {
    if (!data?.logs) return [];
    return data.logs.filter((log: AuditLogEntry) => {
      // Action type filter
      if (actionFilter !== "all" && log.action !== actionFilter) return false;
      // Text search filter
      if (searchFilter.trim()) {
        const q = searchFilter.toLowerCase();
        const matches =
          log.username?.toLowerCase().includes(q) ||
          log.action?.toLowerCase().includes(q) ||
          log.resource_type?.toLowerCase().includes(q) ||
          log.details?.toLowerCase().includes(q);
        if (!matches) return false;
      }
      return true;
    });
  }, [data?.logs, searchFilter, actionFilter]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("audit.title")}</h1>
      <p className="text-gray-500 mb-8">{t("audit.subtitle")}</p>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Search by user, action, resource, or details..."
            className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="all">All Actions</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="delete">Delete</option>
        </select>
      </div>

      {/* Filter scope notice */}
      {(searchFilter || actionFilter !== "all") && (
        <div className="flex items-center gap-2 mb-3 text-xs text-gray-400">
          <Info className="w-3.5 h-3.5" />
          <span>Filters apply to the current page only.</span>
        </div>
      )}

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : !data?.logs?.length ? (
        <EmptyState icon={FileText} message={t("audit.noLogs")} />
      ) : filteredLogs.length === 0 ? (
        <div className="text-center py-12 text-sm text-gray-400">No matching audit logs found.</div>
      ) : (
        <>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-500 border-b bg-gray-50">
                  <th className="px-4 py-3">{t("audit.time")}</th>
                  <th className="px-4 py-3">{t("audit.user")}</th>
                  <th className="px-4 py-3">{t("audit.action")}</th>
                  <th className="px-4 py-3">{t("audit.resource")}</th>
                  <th className="px-4 py-3">Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log: AuditLogEntry) => (
                  <tr key={log.id} className="border-b border-gray-50 last:border-0 text-sm">
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : ""}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-700">{log.username}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${actionColors[log.action] || "bg-gray-50 text-gray-600"}`}>
                        {log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {log.resource_type}
                      {log.resource_id && <span className="text-xs text-gray-400 ml-1">({log.resource_id.substring(0, 8)}...)</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-[200px]">
                      {log.details || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
        </>
      )}
    </div>
  );
}
