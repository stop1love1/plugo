import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, MessageSquare, Clock, Users, Download, Calendar } from "lucide-react";
import api from "../lib/api";
import { useLocale } from "../lib/useLocale";

const getOverview = (siteId: string, days = 30) =>
  api.get(`/analytics/overview?site_id=${siteId}&days=${days}`).then((r) => r.data);
const getMessagesPerDay = (siteId: string, days = 30) =>
  api.get(`/analytics/messages-per-day?site_id=${siteId}&days=${days}`).then((r) => r.data);
const getPopularQuestions = (siteId: string) =>
  api.get(`/analytics/popular-questions?site_id=${siteId}&limit=10`).then((r) => r.data);

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white p-5 rounded-xl border border-gray-200">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="text-2xl font-bold text-gray-900">{value}</div>
          <div className="text-sm text-gray-500">{label}</div>
        </div>
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

export default function Analytics() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const [days, setDays] = useState(30);

  const { data: overview } = useQuery({
    queryKey: ["analytics-overview", siteId, days],
    queryFn: () => getOverview(siteId!, days),
    enabled: !!siteId,
  });

  const { data: chartData = [] } = useQuery({
    queryKey: ["analytics-chart", siteId, days],
    queryFn: () => getMessagesPerDay(siteId!, days),
    enabled: !!siteId,
  });

  const { data: questions = [] } = useQuery({
    queryKey: ["analytics-questions", siteId],
    queryFn: () => getPopularQuestions(siteId!),
    enabled: !!siteId,
  });

  const exportCsv = () => {
    if (!chartData.length) return;
    const csv = "Date,Messages\n" + chartData.map((d: any) => `${d.date},${d.messages}`).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `analytics-${siteId}-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("analytics.title")}</h1>
          <p className="text-gray-500 mt-1">{t("analytics.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Date range picker */}
          <div className="flex items-center bg-white border border-gray-200 rounded-lg overflow-hidden">
            {[
              { label: t("analytics.last7d"), value: 7 },
              { label: t("analytics.last30d"), value: 30 },
              { label: t("analytics.last90d"), value: 90 },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={`px-3 py-1.5 text-xs font-medium ${
                  days === opt.value
                    ? "bg-primary-50 text-primary-700"
                    : "text-gray-500 hover:bg-gray-50"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            onClick={exportCsv}
            className="flex items-center gap-1 text-sm text-gray-600 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50"
          >
            <Download className="w-4 h-4" />
            {t("analytics.exportCsv")}
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={Users}
          label={t("analytics.totalSessions")}
          value={overview?.total_sessions ?? 0}
          color="bg-blue-50 text-blue-600"
        />
        <StatCard
          icon={MessageSquare}
          label={t("analytics.totalMessages")}
          value={overview?.total_messages ?? 0}
          color="bg-purple-50 text-purple-600"
        />
        <StatCard
          icon={TrendingUp}
          label={t("analytics.avgMessages")}
          value={overview?.avg_messages_per_session ?? 0}
          color="bg-green-50 text-green-600"
        />
        <StatCard
          icon={Clock}
          label={t("analytics.avgDuration")}
          value={formatDuration(overview?.avg_session_duration_seconds ?? 0)}
          color="bg-orange-50 text-orange-600"
        />
      </div>

      {/* Messages per day chart */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">{t("analytics.messagesPerDay")}</h3>
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <Calendar className="w-3 h-3" />
            {days} {t("analytics.last30d").split(" ")[1] || "days"}
          </div>
        </div>
        <div className="h-64">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(v) => `Date: ${v}`}
                  formatter={(v: any) => [v, "Messages"]}
                />
                <Bar dataKey="messages" fill="#6366f1" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              {t("analytics.noData")}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Popular questions */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("analytics.popularQuestions")}</h3>
          {questions.length === 0 ? (
            <p className="text-sm text-gray-400">{t("analytics.noData")}</p>
          ) : (
            <div className="space-y-2">
              {questions.map((q: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                  <p className="text-sm text-gray-700 truncate flex-1">{q.question}</p>
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full ml-2 shrink-0">
                    {q.count}x
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Knowledge gaps — questions that couldn't be answered */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("analytics.knowledgeGaps")}</h3>
          <p className="text-sm text-gray-400">{t("analytics.noData")}</p>
          <p className="text-xs text-gray-300 mt-2">
            Coming soon — tracks questions where the bot had no relevant knowledge to answer.
          </p>
        </div>
      </div>
    </div>
  );
}
