import { h } from "preact";
import { useState, useCallback, useRef } from "preact/hooks";
import { Bubble } from "./Bubble";
import { ChatWindow } from "./Window";
import { PlugoWebSocket } from "../lib/websocket";

type Message = {
  role: "user" | "bot";
  content: string;
};

type AppProps = {
  token: string;
  serverUrl: string;
  primaryColor: string;
  greeting: string;
  position: "bottom-right" | "bottom-left";
  getPageContext: () => any;
};

const SESSION_KEY = "plugo_session_";
const VISITOR_KEY = "plugo_visitor_";
const MAX_MESSAGES = 200;

function generateFallbackId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function getSavedSessionId(token: string): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY + token);
  } catch {
    return null;
  }
}

function saveSessionId(token: string, sessionId: string) {
  try {
    sessionStorage.setItem(SESSION_KEY + token, sessionId);
  } catch {
    // sessionStorage unavailable — ignore
  }
}

function getOrCreateVisitorId(token: string): string {
  try {
    const existing = localStorage.getItem(VISITOR_KEY + token);
    if (existing) return existing;
    const id = crypto.randomUUID ? crypto.randomUUID() : generateFallbackId();
    localStorage.setItem(VISITOR_KEY + token, id);
    return id;
  } catch {
    return generateFallbackId();
  }
}

export function App({ token, serverUrl, primaryColor, greeting, position, getPageContext }: AppProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [ws, setWs] = useState<PlugoWebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const isOpenRef = useRef(false);

  const initWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const baseUrl = serverUrl || `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${baseUrl.replace(/^http/, "ws")}/ws/chat/${token}`;

    // Pass saved session_id and visitor_id for server-side session resumption
    const savedSessionId = getSavedSessionId(token);
    const visitorId = getOrCreateVisitorId(token);

    const socket = new PlugoWebSocket(wsUrl, {
      onConnected: (data) => {
        setConnected(true);

        // Save session_id for future reconnections
        if (data.session_id) {
          saveSessionId(token, data.session_id);
          sessionIdRef.current = data.session_id;
        }

        // Set initial suggestions from server
        if (data.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions);
        }

        // Server returned previous messages — restore them
        if (data.resumed && data.history && data.history.length > 0) {
          const restored: Message[] = data.history.map((m: any) => ({
            role: m.role === "user" ? "user" : "bot",
            content: m.content,
          }));
          setMessages(restored);
        } else if (data.greeting && messages.length === 0) {
          // New session — show greeting
          setMessages([{ role: "bot", content: data.greeting }]);
        }
      },
      onStart: () => {
        setIsTyping(true);
        setSuggestions([]); // Clear suggestions during response
        setMessages((prev) => {
          const updated = [...prev, { role: "bot", content: "" }];
          return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
        });
      },
      onToken: (token) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === "bot") {
            updated[updated.length - 1] = {
              ...last,
              content: last.content + token,
            };
          }
          return updated;
        });
      },
      onEnd: (data) => {
        setIsTyping(false);
        // Set follow-up suggestions if provided
        if (data?.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions);
        }
        // Increment unread count if chat window is closed
        if (!isOpenRef.current) {
          setUnreadCount(prev => prev + 1);
        }
      },
      onError: (error) => {
        setIsTyping(false);
        setMessages((prev) => {
          const updated = [
            ...prev,
            { role: "bot", content: `⚠️ ${error}` },
          ];
          return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
        });
      },
    }, savedSessionId, visitorId);

    socket.connect();
    setWs(socket);
  }, [token, serverUrl]);

  const handleOpen = useCallback(() => {
    setIsOpen(true);
    isOpenRef.current = true;
    setUnreadCount(0);
    if (!ws) {
      initWebSocket();
    }
  }, [ws, initWebSocket]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
    isOpenRef.current = false;
  }, []);

  const sessionIdRef = useRef<string | null>(null);

  // Store session_id when connected
  const handleFeedback = useCallback(
    (messageIndex: number, rating: "up" | "down") => {
      const sid = sessionIdRef.current || getSavedSessionId(token);
      if (!sid) return;
      // Fire and forget — send feedback to backend
      const baseUrl = serverUrl || `${window.location.protocol}//${window.location.host}`;
      const httpUrl = baseUrl.replace(/^ws/, "http");
      fetch(`${httpUrl}/api/sessions/${sid}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_index: messageIndex, rating }),
      }).catch(() => {});
    },
    [token, serverUrl]
  );

  const handleFileUpload = useCallback(
    (file: File) => {
      // For now, send the file name as a message — full file upload requires backend support
      const message = `[Attached file: ${file.name} (${(file.size / 1024).toFixed(1)}KB)]`;
      setMessages((prev) => [...prev, { role: "user", content: message }]);
      if (ws) {
        ws.send(message, getPageContext());
      }
    },
    [ws, getPageContext]
  );

  const handleSend = useCallback(
    (message: string) => {
      if (!ws || !message.trim()) return;

      setSuggestions([]); // Clear suggestions when user sends
      setMessages((prev) => {
        const updated = [...prev, { role: "user", content: message }];
        return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
      });
      ws.send(message, getPageContext());
    },
    [ws, getPageContext]
  );

  return (
    <div>
      {isOpen && (
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          position={position}
          suggestions={suggestions}
          onSend={handleSend}
          onClose={handleClose}
          onFeedback={handleFeedback}
          onFileUpload={handleFileUpload}
        />
      )}
      <Bubble
        position={position}
        isOpen={isOpen}
        unreadCount={unreadCount}
        onClick={isOpen ? handleClose : handleOpen}
      />
    </div>
  );
}
