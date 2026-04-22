import { useState, useCallback, useRef, useEffect } from "preact/hooks";
import { Bubble } from "./Bubble";
import { ChatWindow } from "./Window";
import { PlugoWebSocket, ConnectionState, type WsHistoryItem, type Citation } from "../websocket";

type Message = {
  role: "user" | "bot";
  content: string;
  timestamp: number;
  citations?: Citation[];
};

type AppProps = {
  token: string;
  serverUrl: string;
  primaryColor: string;
  greeting: string;
  position: "bottom-right" | "bottom-left";
  widgetTitle?: string;
  botAvatar?: string;
  headerSubtitle?: string;
  inputPlaceholder?: string;
  autoOpenDelay?: number;
  bubbleSize?: string;
  getPageContext: () => Record<string, unknown>;
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

// Sliding 30-day window. Visitor ids expire so a browser that stops visiting
// can't be silently linked to the site forever.
const VISITOR_TTL_MS = 30 * 86400 * 1000;

function _newVisitorId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : generateFallbackId();
}

function getOrCreateVisitorId(token: string): string {
  const storageKey = VISITOR_KEY + token;
  try {
    const existing = localStorage.getItem(storageKey);
    if (existing) {
      try {
        const parsed = JSON.parse(existing) as { id?: string; exp?: number };
        if (
          parsed &&
          typeof parsed.id === "string" &&
          typeof parsed.exp === "number" &&
          parsed.exp > Date.now()
        ) {
          // Sliding window — bump expiry on each use.
          const refreshed = { id: parsed.id, exp: Date.now() + VISITOR_TTL_MS };
          localStorage.setItem(storageKey, JSON.stringify(refreshed));
          return parsed.id;
        }
      } catch {
        // Legacy plain-string id; migrate into the wrapped format below.
        if (typeof existing === "string" && existing && !existing.startsWith("{")) {
          const wrapped = { id: existing, exp: Date.now() + VISITOR_TTL_MS };
          localStorage.setItem(storageKey, JSON.stringify(wrapped));
          return existing;
        }
      }
    }
    const id = _newVisitorId();
    localStorage.setItem(storageKey, JSON.stringify({ id, exp: Date.now() + VISITOR_TTL_MS }));
    return id;
  } catch {
    return generateFallbackId();
  }
}

/** Expose a global helper so cookie-consent integrations can revoke the visitor id. */
declare global {
  interface Window {
    plugoClearVisitorId?: () => void;
  }
}
if (typeof window !== "undefined") {
  window.plugoClearVisitorId = () => {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && key.startsWith(VISITOR_KEY)) {
          localStorage.removeItem(key);
        }
      }
    } catch {
      // storage unavailable — nothing to do
    }
  };
}

let _audioCtx: AudioContext | null = null;
function getAudioContext(): AudioContext | null {
  try {
    if (!_audioCtx) {
      const Ctx =
        window.AudioContext ||
        (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctx) return null;
      _audioCtx = new Ctx();
    }
    return _audioCtx;
  } catch {
    return null;
  }
}

function playNotificationSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  if (ctx.state === "suspended") {
    ctx.resume();
  }
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = 800;
  gain.gain.value = 0.1;
  osc.onended = () => osc.disconnect();
  osc.start();
  osc.stop(ctx.currentTime + 0.1);
}

export function App({
  token,
  serverUrl,
  primaryColor: _primaryColor,
  greeting: _greeting,
  position,
  widgetTitle,
  botAvatar,
  headerSubtitle,
  inputPlaceholder,
  autoOpenDelay,
  bubbleSize,
  getPageContext,
}: AppProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [ws, setWs] = useState<PlugoWebSocket | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const isOpenRef = useRef(false);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const sessionIdRef = useRef<string | null>(null);

  // Auto-open after delay
  useEffect(() => {
    if (autoOpenDelay && autoOpenDelay > 0) {
      const timer = setTimeout(() => {
        if (!isOpenRef.current) {
          setIsOpen(true);
          isOpenRef.current = true;
        }
      }, autoOpenDelay * 1000);
      return () => clearTimeout(timer);
    }
  }, [autoOpenDelay]);

  const initWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const baseUrl = serverUrl || `${wsProtocol}//${window.location.host}`;
    // site_token is now sent in the init message, not embedded in the URL.
    const wsUrl = `${baseUrl.replace(/^http/, "ws")}/ws/chat`;

    const savedSessionId = getSavedSessionId(token);
    const visitorId = getOrCreateVisitorId(token);

    const socket = new PlugoWebSocket(wsUrl, token, {
      onConnected: (data) => {
        if (data.session_id) {
          saveSessionId(token, data.session_id);
          sessionIdRef.current = data.session_id;
        }

        if (data.suggestions && data.suggestions.length > 0) {
          setSuggestions(data.suggestions);
        }

        if (data.resumed && data.history && data.history.length > 0) {
          const restored: Message[] = data.history.map((m: WsHistoryItem) => ({
            role: (m.role === "user" ? "user" : "bot") as Message["role"],
            content: m.content ?? "",
            timestamp: m.timestamp ?? Date.now(),
          }));
          setMessages(restored);
        } else if (data.greeting && messagesRef.current.length === 0) {
          setMessages([{ role: "bot" as const, content: data.greeting, timestamp: Date.now() }]);
        }
      },
      onStart: () => {
        setIsTyping(true);
        setSuggestions([]);
        setMessages((prev) => {
          // Guard against double onStart: don't push if last message is already an empty bot message
          const last = prev[prev.length - 1];
          if (last && last.role === "bot" && last.content === "") {
            return prev;
          }
          const updated = [...prev, { role: "bot" as const, content: "", timestamp: Date.now() }];
          return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
        });
      },
      onToken: (token) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          // Only append if the last message is a bot message
          if (!last || last.role !== "bot") return prev;
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...last,
            content: last.content + token,
          };
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
        if (document.hidden) {
          playNotificationSound();
        }
      },
      onCitations: (items) => {
        // Attach to the last assistant message (citations arrive before "end").
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (!last || last.role !== "bot") return prev;
          const updated = [...prev];
          updated[updated.length - 1] = { ...last, citations: items };
          return updated;
        });
      },
      onError: (error) => {
        setIsTyping(false);
        setMessages((prev) => {
          const updated = [
            ...prev,
            { role: "bot" as const, content: `\u26a0\ufe0f ${error}`, timestamp: Date.now() },
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

  // Cleanup WebSocket on unmount (e.g. host page navigation while chat is open)
  useEffect(() => {
    return () => {
      ws?.disconnect();
    };
  }, [ws]);

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
    // Disconnect WebSocket when closing to prevent memory leaks
    if (ws) {
      ws.disconnect();
      setWs(null);
    }
  }, [ws]);

  const handleMinimize = useCallback(() => {
    setIsOpen(false);
    isOpenRef.current = false;
    // Keep WS alive — user just minimized, not closed
  }, []);

  const handleFeedback = useCallback(
    (messageIndex: number, rating: "up" | "down") => {
      const sid = sessionIdRef.current || getSavedSessionId(token);
      if (!sid) return;
      const baseUrl = serverUrl || `${window.location.protocol}//${window.location.host}`;
      const httpUrl = baseUrl.replace(/^ws/, "http");
      // Site token goes in Authorization so it doesn't leak into server/CDN
      // access logs or Referer headers the way query strings do.
      fetch(`${httpUrl}/api/sessions/${sid}/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message_index: messageIndex, rating }),
      }).catch(() => {});
    },
    [token, serverUrl]
  );

  const handleSend = useCallback(
    (message: string) => {
      if (!ws || !message.trim()) return;

      // Check connection BEFORE adding message to state
      const sent = ws.send(message, getPageContext());
      if (!sent) {
        setMessages((prev) => [
          ...prev,
          { role: "bot" as const, content: "\u26a0\ufe0f Message could not be sent. Please check your connection.", timestamp: Date.now() },
        ]);
        return;
      }

      setSuggestions([]);
      setMessages((prev) => {
        const updated = [...prev, { role: "user" as const, content: message, timestamp: Date.now() }];
        return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
      });
    },
    [ws, getPageContext]
  );

  const handleRetry = useCallback(
    (errorIndex: number) => {
      // Find the last user message before this error
      let lastUserMsg = "";
      const currentMessages = messagesRef.current;
      for (let j = errorIndex - 1; j >= 0; j--) {
        if (currentMessages[j].role === "user") {
          lastUserMsg = currentMessages[j].content;
          break;
        }
      }
      if (!lastUserMsg) return;

      // Remove the error message first, then resend
      setMessages((prev) => prev.filter((_, i) => i !== errorIndex));
      handleSend(lastUserMsg);
    },
    [handleSend]
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
          widgetTitle={widgetTitle}
          botAvatar={botAvatar}
          headerSubtitle={headerSubtitle}
          inputPlaceholder={inputPlaceholder}
          onSend={handleSend}
          onClose={handleClose}
          onMinimize={handleMinimize}
          onFeedback={handleFeedback}
          onRetry={handleRetry}
        />
      )}
      <Bubble
        position={position}
        isOpen={isOpen}
        unreadCount={unreadCount}
        bubbleSize={bubbleSize}
        onClick={isOpen ? handleMinimize : handleOpen}
      />
    </div>
  );
}
