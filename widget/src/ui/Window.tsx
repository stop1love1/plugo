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
  suggestions: string[];
  onSend: (message: string) => void;
  onClose: () => void;
};

export function ChatWindow({ messages, isTyping, position, suggestions, onSend, onClose }: WindowProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping, suggestions]);

  // Focus input when opened
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

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

      <div class="plugo-messages" role="log" aria-live="polite" aria-label="Chat messages">
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

        {/* Suggestion buttons */}
        {suggestions.length > 0 && !isTyping && (
          <div class="plugo-suggestions">
            {suggestions.map((s, i) => (
              <button
                key={i}
                class="plugo-suggestion-btn"
                onClick={() => onSend(s)}
              >
                {s}
              </button>
            ))}
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
          placeholder="Type a message..."
          disabled={isTyping}
        />
        <button type="submit" disabled={!input.trim() || isTyping}>
          Send
        </button>
      </form>
    </div>
  );
}
