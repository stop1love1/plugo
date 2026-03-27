import { h } from "preact";
import { useState, useCallback } from "preact/hooks";
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

export function App({ token, serverUrl, primaryColor, greeting, position, getPageContext }: AppProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [ws, setWs] = useState<PlugoWebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  const initWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const baseUrl = serverUrl || `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${baseUrl.replace(/^http/, "ws")}/ws/chat/${token}`;

    const socket = new PlugoWebSocket(wsUrl, {
      onConnected: (data) => {
        setConnected(true);
        if (data.greeting && messages.length === 0) {
          setMessages([{ role: "bot", content: data.greeting }]);
        }
      },
      onStart: () => {
        setIsTyping(true);
        setMessages((prev) => [...prev, { role: "bot", content: "" }]);
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
      onEnd: () => {
        setIsTyping(false);
      },
      onError: (error) => {
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          { role: "bot", content: `⚠️ ${error}` },
        ]);
      },
    });

    socket.connect();
    setWs(socket);
  }, [token, serverUrl]);

  const handleOpen = useCallback(() => {
    setIsOpen(true);
    if (!ws) {
      initWebSocket();
    }
  }, [ws, initWebSocket]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleSend = useCallback(
    (message: string) => {
      if (!ws || !message.trim()) return;

      setMessages((prev) => [...prev, { role: "user", content: message }]);
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
          onSend={handleSend}
          onClose={handleClose}
        />
      )}
      <Bubble
        position={position}
        isOpen={isOpen}
        onClick={isOpen ? handleClose : handleOpen}
      />
    </div>
  );
}
