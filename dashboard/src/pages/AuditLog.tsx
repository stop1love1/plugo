import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuditLogs } from "../lib/api";
import { FileText, User, Clock } from "lucide-react";
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

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", page],
    queryFn: () => getAuditLogs(page),
  });

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("audit.title")}</h1>
      <p className="text-gray-500 mb-8">{t("audit.subtitle")}</p>

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : !data?.logs?.length ? (
        <EmptyState icon={FileText} message={t("audit.noLogs")} />
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
                {data.logs.map((log: any) => (
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
