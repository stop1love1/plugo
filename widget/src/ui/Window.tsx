import { h } from "preact";
import { useState, useRef, useEffect } from "preact/hooks";
import { Message } from "./Message";

type ChatMessage = {
  role: "user" | "bot";
  content: string;
};

type WindowProps = {
  messages: ChatMessage[];
  isTyping: boolean;
  position: "bottom-right" | "bottom-left";
  onSend: (message: string) => void;
  onClose: () => void;
};

export function ChatWindow({ messages, isTyping, position, onSend, onClose }: WindowProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // Focus input when opened
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <div class={`plugo-window ${position}`}>
      <div class="plugo-header">
        <h3>Plugo Chat</h3>
        <button onClick={onClose} aria-label="Close">&times;</button>
      </div>

      <div class="plugo-messages">
        {messages.map((msg, i) => (
          <Message key={i} role={msg.role} content={msg.content} />
        ))}
        {isTyping && messages[messages.length - 1]?.content === "" && (
          <div class="plugo-typing">
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form class="plugo-input-area" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onInput={(e) => setInput((e.target as HTMLInputElement).value)}
          placeholder="Nhập tin nhắn..."
          disabled={isTyping}
        />
        <button type="submit" disabled={!input.trim() || isTyping}>
          Gửi
        </button>
      </form>
    </div>
  );
}
