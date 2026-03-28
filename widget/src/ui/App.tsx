import { h } from "preact";
import { useState, useCallback, useRef } from "preact/hooks";
import { Bubble } from "./Bubble";
import { ChatWindow } from "./Window";
import { PlugoWebSocket, ConnectionState } from "../lib/websocket";

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
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const isOpenRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);

  const initWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const baseUrl = serverUrl || `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${baseUrl.replace(/^http/, "ws")}/ws/chat/${token}`;

    const savedSessionId = getSavedSessionId(token);
    const visitorId = getOrCreateVisitorId(token);

    const socket = new PlugoWebSocket(wsUrl, {
      onConnected: (data) => {
        if (data.session_id) {
          saveSessionId(token, data.session_id);
          sessionIdRef.current = data.session_id;
        }

        if (data.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions);
        }

        if (data.resumed && data.history && data.history.length > 0) {
          const restored: Message[] = data.history.map((m: any) => ({
            role: m.role === "user" ? "user" : "bot",
            content: m.content,
          }));
          setMessages(restored);
        } else if (data.greeting && messages.length === 0) {
          setMessages([{ role: "bot", content: data.greeting }]);
        }
      },
      onStart: () => {
        setIsTyping(true);
        setSuggestions([]);
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
        if (data?.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions);
        }
        if (!isOpenRef.current) {
          setUnreadCount(prev => prev + 1);
        }
      },
      onError: (error) => {
        setIsTyping(false);
        setMessages((prev) => {
          const updated = [
            ...prev,
            { role: "bot", content: `\u26a0\ufe0f ${error}` },
          ];
          return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
        });
      },
      onConnectionChange: (state) => {
        setConnectionState(state);
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

  const handleFeedback = useCallback(
    (messageIndex: number, rating: "up" | "down") => {
      const sid = sessionIdRef.current || getSavedSessionId(token);
      if (!sid) return;
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

  const handleSend = useCallback(
    (message: string) => {
      if (!ws || !message.trim()) return;

      setSuggestions([]);
      setMessages((prev) => {
        const updated = [...prev, { role: "user", content: message }];
        return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
      });
      const sent = ws.send(message, getPageContext());
      if (!sent) {
        // Message failed to send — notify user
        setMessages((prev) => [
          ...prev,
          { role: "bot", content: "\u26a0\ufe0f Message could not be sent. Please check your connection." },
        ]);
      }
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
          connectionState={connectionState}
          onSend={handleSend}
          onClose={handleClose}
          onFeedback={handleFeedback}
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
