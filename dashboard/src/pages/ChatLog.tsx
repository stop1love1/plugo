import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSessions, getSession } from "../lib/api";
import { MessageCircle, User, Bot } from "lucide-react";

export default function ChatLog() {
  const { siteId } = useParams<{ siteId: string }>();
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

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

  return (
    <div className="max-w-5xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Chat Log</h1>
      <p className="text-gray-500 mb-8">Xem lịch sử chat của khách truy cập</p>

      <div className="flex gap-6">
        {/* Session list */}
        <div className="w-80 flex-shrink-0">
          {isLoading ? (
            <div className="text-gray-400">Đang tải...</div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
              <MessageCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-sm text-gray-500">Chưa có chat session nào</p>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map((s: any) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedSession === s.id
                      ? "border-primary-300 bg-primary-50"
                      : "border-gray-200 bg-white hover:border-gray-300"
                  }`}
                >
                  <div className="text-sm font-medium text-gray-900">
                    {s.message_count} tin nhắn
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {s.started_at ? new Date(s.started_at).toLocaleString("vi-VN") : ""}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Message detail */}
        <div className="flex-1">
          {selectedSession && sessionDetail?.messages ? (
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 max-h-[600px] overflow-y-auto">
              {sessionDetail.messages.map((msg: any, i: number) => (
                <div key={i} className={`flex gap-3 ${msg.role === "user" ? "" : ""}`}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === "user" ? "bg-blue-100" : "bg-purple-100"
                  }`}>
                    {msg.role === "user"
                      ? <User className="w-3.5 h-3.5 text-blue-600" />
                      : <Bot className="w-3.5 h-3.5 text-purple-600" />}
                  </div>
                  <div className="flex-1">
                    <span className="text-xs font-medium text-gray-500">
                      {msg.role === "user" ? "Khách" : "Bot"}
                    </span>
                    <p className="text-sm text-gray-800 mt-0.5 whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-20 text-gray-400 text-sm">
              Chọn một session để xem chi tiết
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
