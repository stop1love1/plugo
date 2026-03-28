import { h } from "preact";
import { useState, useCallback, useRef, useEffect } from "preact/hooks";
import { Bubble } from "./Bubble";
import { ChatWindow } from "./Window";
import { PlugoWebSocket, ConnectionState } from "../lib/websocket";

type Message = {
  role: "user" | "bot";
  content: string;
  timestamp: number;
};

type AppProps = {
  token: string;
  serverUrl: string;
  primaryColor: string;
  greeting: string;
  position: "bottom-right" | "bottom-left";
  widgetTitle?: string;
  showBranding?: boolean;
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

let _audioCtx: AudioContext | null = null;
function getAudioContext(): AudioContext | null {
  try {
    if (!_audioCtx) {
      _audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    return _audioCtx;
  } catch {
    return null;
  }
}

function playNotificationSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = 800;
  gain.gain.value = 0.1;
  osc.start();
  osc.stop(ctx.currentTime + 0.1);
}

export function App({ token, serverUrl, primaryColor, greeting, position, widgetTitle, showBranding = true, getPageContext }: AppProps) {
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
            timestamp: m.timestamp || Date.now(),
          }));
          setMessages(restored);
        } else if (data.greeting && messagesRef.current.length === 0) {
          setMessages([{ role: "bot", content: data.greeting, timestamp: Date.now() }]);
        }
      },
      onStart: () => {
        setIsTyping(true);
        setSuggestions([]);
        setMessages((prev) => {
          const updated = [...prev, { role: "bot", content: "", timestamp: Date.now() }];
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
        if (document.hidden) {
          playNotificationSound();
        }
      },
      onError: (error) => {
        setIsTyping(false);
        setMessages((prev) => {
          const updated = [
            ...prev,
            { role: "bot", content: `\u26a0\ufe0f ${error}`, timestamp: Date.now() },
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
      fetch(`${httpUrl}/api/sessions/${sid}/feedback?site_token=${encodeURIComponent(token)}`, {
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
        const updated = [...prev, { role: "user", content: message, timestamp: Date.now() }];
        return updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
      });
      const sent = ws.send(message, getPageContext());
      if (!sent) {
        // Message failed to send — notify user
        setMessages((prev) => [
          ...prev,
          { role: "bot", content: "\u26a0\ufe0f Message could not be sent. Please check your connection.", timestamp: Date.now() },
        ]);
      }
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
          showBranding={showBranding}
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
        onClick={isOpen ? handleClose : handleOpen}
      />
    </div>
  );
}
