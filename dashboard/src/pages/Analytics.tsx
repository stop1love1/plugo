import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, MessageSquare, Clock, Users } from "lucide-react";
import api from "../lib/api";

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

  const { data: overview } = useQuery({
    queryKey: ["analytics-overview", siteId],
    queryFn: () => getOverview(siteId!),
    enabled: !!siteId,
  });

  const { data: chartData = [] } = useQuery({
    queryKey: ["analytics-chart", siteId],
    queryFn: () => getMessagesPerDay(siteId!),
    enabled: !!siteId,
  });

  const { data: questions = [] } = useQuery({
    queryKey: ["analytics-questions", siteId],
    queryFn: () => getPopularQuestions(siteId!),
    enabled: !!siteId,
  });

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Analytics</h1>
      <p className="text-gray-500 mb-8">Chat performance and usage insights</p>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={Users}
          label="Total Sessions"
          value={overview?.total_sessions ?? 0}
          color="bg-blue-50 text-blue-600"
        />
        <StatCard
          icon={MessageSquare}
          label="Total Messages"
          value={overview?.total_messages ?? 0}
          color="bg-purple-50 text-purple-600"
        />
        <StatCard
          icon={TrendingUp}
          label="Avg Messages/Session"
          value={overview?.avg_messages_per_session ?? 0}
          color="bg-green-50 text-green-600"
        />
        <StatCard
          icon={Clock}
          label="Avg Duration"
          value={formatDuration(overview?.avg_session_duration_seconds ?? 0)}
          color="bg-orange-50 text-orange-600"
        />
      </div>

      {/* Messages per day chart */}
      <div className="bg-white p-6 rounded-xl border border-gray-200 mb-8">
        <h3 className="font-semibold mb-4">Messages per Day (Last 30 days)</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11 }}
                tickFormatter={(v) => v.slice(5)}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(v) => `Date: ${v}`}
                formatter={(v: number) => [v, "Messages"]}
              />
              <Bar dataKey="messages" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Popular questions */}
      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="font-semibold mb-4">Popular Questions</h3>
        {questions.length === 0 ? (
          <p className="text-sm text-gray-400">No data yet</p>
        ) : (
          <div className="space-y-2">
            {questions.map((q: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <p className="text-sm text-gray-700 truncate flex-1">{q.question}</p>
                <span className="text-xs text-gray-400 ml-4 shrink-0">{q.count}x</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
