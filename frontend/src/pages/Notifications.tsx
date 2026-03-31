import { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle, XCircle, Info, Trash2 } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { useLocale } from "../lib/useLocale";
import { useNotifications } from "../lib/useNotifications";
import type { Notification } from "../lib/notifications";

type TypeFilter = "all" | Notification["type"];

function formatRelativeTime(timestamp: number, locale: string): string {
  const diffMs = Date.now() - timestamp;
  const diffSec = Math.round(diffMs / 1000);
  const loc = locale === "vi" ? "vi-VN" : "en-US";
  const rtf = new Intl.RelativeTimeFormat(loc, { numeric: "auto" });
  if (Math.abs(diffSec) < 45) return rtf.format(-Math.max(diffSec, 1), "second");
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) return rtf.format(-diffMin, "minute");
  const diffHr = Math.round(diffMin / 60);
  if (Math.abs(diffHr) < 36) return rtf.format(-diffHr, "hour");
  const diffDay = Math.round(diffHr / 24);
  if (Math.abs(diffDay) < 30) return rtf.format(-diffDay, "day");
  return new Date(timestamp).toLocaleString(loc);
}

export default function Notifications() {
  const { t, locale } = useLocale();
  const { notifications, markAllRead, clearAll, removeOne } = useNotifications();
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  useEffect(() => {
    markAllRead();
  }, [markAllRead]);

  const filtered = useMemo(() => {
    if (typeFilter === "all") return notifications;
    return notifications.filter((n) => n.type === typeFilter);
  }, [notifications, typeFilter]);

  const counts = useMemo(() => {
    const c = { success: 0, error: 0, info: 0 };
    for (const n of notifications) {
      if (n.type === "success") c.success++;
      else if (n.type === "error") c.error++;
      else c.info++;
    }
    return c;
  }, [notifications]);

  const filterPills: { id: TypeFilter; label: string; count?: number }[] = [
    { id: "all", label: t("notifications.filterAll") },
    { id: "success", label: t("notifications.filterSuccess"), count: counts.success },
    { id: "error", label: t("notifications.filterError"), count: counts.error },
    { id: "info", label: t("notifications.filterInfo"), count: counts.info },
  ];

  return (
    <div className="flex flex-col h-[calc(100dvh-7rem)] min-h-[24rem] lg:h-[calc(100dvh-5.5rem)] lg:min-h-[28rem]">
      <PageHeader title={t("notifications.title")} subtitle={t("notifications.subtitle")} className="mb-4 shrink-0">
        {notifications.length > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex items-center gap-2 text-sm text-red-600 hover:text-red-800 px-3 py-2 rounded-lg border border-red-200 hover:bg-red-50"
          >
            <Trash2 className="w-4 h-4" />
            {t("notifications.clearAll")}
          </button>
        )}
      </PageHeader>

      {notifications.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 shrink-0">
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">{t("notifications.summary")}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{notifications.length}</p>
              <p className="text-xs text-gray-500 mt-0.5">{t("notifications.items")}</p>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700/80">{t("notifications.filterSuccess")}</p>
              <p className="text-2xl font-bold text-emerald-800 mt-1">{counts.success}</p>
            </div>
            <div className="rounded-xl border border-red-100 bg-red-50/60 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-red-700/80">{t("notifications.filterError")}</p>
              <p className="text-2xl font-bold text-red-800 mt-1">{counts.error}</p>
            </div>
            <div className="rounded-xl border border-sky-100 bg-sky-50/60 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-700/80">{t("notifications.filterInfo")}</p>
              <p className="text-2xl font-bold text-sky-800 mt-1">{counts.info}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mb-3 shrink-0">
            {filterPills.map((pill) => (
              <button
                key={pill.id}
                type="button"
                onClick={() => setTypeFilter(pill.id)}
                className={`inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition-colors ${
                  typeFilter === pill.id
                    ? "bg-primary-600 text-white border-primary-600 shadow-sm"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                {pill.label}
                {pill.count != null && pill.id !== "all" ? (
                  <span
                    className={`tabular-nums rounded-full px-1.5 py-0.5 text-[10px] ${
                      typeFilter === pill.id ? "bg-white/20 text-white" : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {pill.count}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        {notifications.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-6">
            <EmptyState icon={Bell} message={t("notifications.empty")} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-8 text-sm text-gray-500">{t("common.noResults")}</div>
        ) : (
          <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-gray-100">
            {filtered.map((n) => {
              const borderClass =
                n.type === "success"
                  ? "border-l-emerald-500"
                  : n.type === "error"
                    ? "border-l-red-500"
                    : "border-l-sky-500";
              return (
                <li
                  key={n.id}
                  className={`flex items-start gap-4 p-4 pl-3 border-l-4 ${borderClass} ${!n.read ? "bg-slate-50/80" : "bg-white"}`}
                >
                  <div className="mt-0.5 shrink-0">
                    {n.type === "success" ? (
                      <div className="w-9 h-9 rounded-full bg-emerald-100 flex items-center justify-center">
                        <CheckCircle className="w-5 h-5 text-emerald-600" />
                      </div>
                    ) : n.type === "error" ? (
                      <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center">
                        <XCircle className="w-5 h-5 text-red-600" />
                      </div>
                    ) : (
                      <div className="w-9 h-9 rounded-full bg-sky-100 flex items-center justify-center">
                        <Info className="w-5 h-5 text-sky-600" />
                      </div>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900">{n.title}</p>
                    {n.message && (
                      <p className="text-sm text-gray-600 mt-1.5 whitespace-pre-wrap break-words leading-relaxed">{n.message}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-2" title={new Date(n.timestamp).toLocaleString(locale === "vi" ? "vi-VN" : "en-US")}>
                      {formatRelativeTime(n.timestamp, locale)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeOne(n.id)}
                    className="text-gray-400 hover:text-red-600 p-2 rounded-lg hover:bg-red-50 shrink-0 transition-colors"
                    aria-label={t("common.delete")}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
