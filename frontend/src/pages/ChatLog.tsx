import { useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSessions, getSession, type ChatSession } from "../lib/api";
import { MessageCircle, User, Bot, Search, Globe, Clock, Download } from "lucide-react";
import { useLocale } from "../lib/useLocale";
import { SkeletonList } from "../components/Skeleton";

function formatDuration(startedAt: string, endedAt?: string | null): string {
  if (!startedAt) return "";
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const diffMs = end - start;
  const mins = Math.floor(diffMs / 60000);
  const secs = Math.floor((diffMs % 60000) / 1000);
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

export default function ChatLog() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions", siteId],
    queryFn: () => getSessions(siteId!),
    enabled: !!siteId,
  });

  const { data: sessionDetail } = useQuery({
    queryKey: ["session", selectedSession],
    queryFn: () => getSession(selectedSession!),
    enabled: !!selectedSession,
  });

  // Filter sessions by search query and date range
  const filteredSessions = useMemo(() => {
    return sessions.filter((s: ChatSession) => {
      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesText =
          s.visitor_id?.toLowerCase().includes(q) ||
          s.page_url?.toLowerCase().includes(q) ||
          s.first_message?.toLowerCase().includes(q);
        if (!matchesText) return false;
      }
      // Date filter
      if (dateFrom && s.started_at) {
        if (new Date(s.started_at) < new Date(dateFrom)) return false;
      }
      if (dateTo && s.started_at) {
        const toEnd = new Date(dateTo);
        toEnd.setDate(toEnd.getDate() + 1);
        if (new Date(s.started_at) >= toEnd) return false;
      }
      return true;
    });
  }, [sessions, searchQuery, dateFrom, dateTo]);

  const exportSessionCsv = () => {
    if (!sessionDetail?.messages) return;
    const rows = sessionDetail.messages.map((msg: { role: string; content: string; timestamp?: string; created_at?: string }) => {
      const content = (msg.content || "").replace(/"/g, '""');
      const timestamp = msg.created_at || "";
      return `"${timestamp}","${msg.role}","${content}"`;
    });
    const csv = "Timestamp,Role,Content\n" + rows.join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-session-${selectedSession}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("chatLog.title")}</h1>
      <p className="text-gray-500 mb-6">{t("chatLog.subtitle")}</p>

      {/* Search + Date Filters */}
      <div className="space-y-3 mb-6">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("chatLog.searchMessages")}
            className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 shrink-0">From:</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 shrink-0">To:</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          {(dateFrom || dateTo) && (
            <button
              onClick={() => { setDateFrom(""); setDateTo(""); }}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Clear dates
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Session list */}
        <div className="w-full lg:w-80 lg:flex-shrink-0">
          {isLoading ? (
            <SkeletonList items={4} />
          ) : filteredSessions.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <MessageCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">{searchQuery ? t("common.noResults") : t("chatLog.noSessions")}</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[calc(100dvh-200px)] overflow-y-auto">
              {filteredSessions.map((s: ChatSession) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedSession === s.id
                      ? "border-primary-300 bg-primary-50"
                      : "border-gray-200 bg-white hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900">
                      {s.message_count || s.messages?.length || 0} {t("chatLog.messages")}
                    </span>
                    {s.started_at && s.ended_at && (
                      <span className="text-xs text-gray-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDuration(s.started_at, s.ended_at)}
                      </span>
                    )}
                  </div>

                  {/* Visitor ID */}
                  {s.visitor_id && (
                    <div className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                      <User className="w-3 h-3" />
                      <span className="truncate max-w-[200px]">{s.visitor_id}</span>
                    </div>
                  )}

                  {/* Page URL */}
                  {s.page_url && (
                    <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                      <Globe className="w-3 h-3" />
                      <span className="truncate max-w-[200px]">{s.page_url}</span>
                    </div>
                  )}

                  <div className="text-xs text-gray-400 mt-1">
                    {s.started_at ? new Date(s.started_at).toLocaleString() : ""}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Message detail */}
        <div className="flex-1">
          {selectedSession && sessionDetail?.messages ? (
            <div>
              {/* Export button */}
              <div className="flex justify-end mb-2">
                <button
                  onClick={exportSessionCsv}
                  className="flex items-center gap-1 text-sm text-gray-600 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50"
                >
                  <Download className="w-4 h-4" />
                  Export CSV
                </button>
              </div>
              {/* Session metadata */}
              {(sessionDetail.visitor_id || sessionDetail.page_url) && (
                <div className="bg-gray-50 p-3 rounded-lg border border-gray-200 mb-3 text-xs text-gray-500 space-y-1">
                  {sessionDetail.visitor_id && (
                    <div className="flex items-center gap-2">
                      <User className="w-3 h-3" />
                      <span className="font-medium">{t("chatLog.visitor")}:</span>
                      <span className="font-mono">{sessionDetail.visitor_id}</span>
                    </div>
                  )}
                  {sessionDetail.page_url && (
                    <div className="flex items-center gap-2">
                      <Globe className="w-3 h-3" />
                      <span className="font-medium">{t("chatLog.page")}:</span>
                      <a href={sessionDetail.page_url} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline truncate">
                        {sessionDetail.page_url}
                      </a>
                    </div>
                  )}
                  {sessionDetail.started_at && (
                    <div className="flex items-center gap-2">
                      <Clock className="w-3 h-3" />
                      <span className="font-medium">{t("chatLog.duration")}:</span>
                      <span>{formatDuration(sessionDetail.started_at, sessionDetail.ended_at)}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 max-h-[calc(100dvh-200px)] overflow-y-auto">
                {sessionDetail.messages.map((msg: { role: string; content: string; timestamp?: string }, i: number) => (
                  <div key={`${msg.role}-${msg.timestamp ?? i}`} className="flex gap-3">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                      msg.role === "user" ? "bg-blue-100" : "bg-purple-100"
                    }`}>
                      {msg.role === "user"
                        ? <User className="w-3.5 h-3.5 text-blue-600" />
                        : <Bot className="w-3.5 h-3.5 text-purple-600" />}
                    </div>
                    <div className="flex-1">
                      <span className="text-xs font-medium text-gray-500">
                        {msg.role === "user" ? t("chatLog.visitor") : t("chatLog.bot")}
                      </span>
                      <p className="text-sm text-gray-800 mt-0.5 whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center py-20 text-gray-400 text-sm">
              {t("chatLog.selectSession")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
