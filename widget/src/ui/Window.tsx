import { h } from "preact";
import { useState, useRef, useEffect, useCallback } from "preact/hooks";
import { Message } from "./Message";
import { getWidgetString, detectLanguage } from "../lib/i18n";
import type { ConnectionState } from "../lib/websocket";

const MAX_INPUT_LENGTH = 500;

type ChatMessage = {
  role: "user" | "bot";
  content: string;
  timestamp: number;
};

type WindowProps = {
  messages: ChatMessage[];
  isTyping: boolean;
  position: "bottom-right" | "bottom-left";
  suggestions: string[];
  connectionState: ConnectionState;
  onSend: (message: string) => void;
  onClose: () => void;
  onFeedback?: (index: number, rating: "up" | "down") => void;
  onRetry?: (errorIndex: number) => void;
};

export function ChatWindow({ messages, isTyping, position, suggestions, connectionState, onSend, onClose, onFeedback, onRetry }: WindowProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const windowRef = useRef<HTMLDivElement>(null);
  const lang = detectLanguage();
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const [newMessageCount, setNewMessageCount] = useState(0);

  const isOffline = connectionState === "disconnected" || connectionState === "reconnecting";

  // Smart auto-scroll: only scroll if user is near bottom
  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    } else {
      setNewMessageCount((c) => c + 1);
    }
  }, [userScrolledUp]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // Detect manual scroll
  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distFromBottom > 100) {
      setUserScrolledUp(true);
    } else {
      setUserScrolledUp(false);
      setNewMessageCount(0);
    }
  }, []);

  const jumpToBottom = () => {
    setUserScrolledUp(false);
    setNewMessageCount(0);
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

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

  // Focus trap: keep Tab cycling within the widget window
  useEffect(() => {
    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const focusable = windowRef.current?.querySelectorAll<HTMLElement>(
        'button, input, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleTab);
    return () => document.removeEventListener('keydown', handleTab);
  }, []);

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    if (!input.trim() || isTyping || isOffline) return;
    onSend(input.trim());
    setInput("");
  };

  const handleInput = (e: Event) => {
    const val = (e.target as HTMLInputElement).value;
    if (val.length <= MAX_INPUT_LENGTH) {
      setInput(val);
    }
  };

  return (
    <div class={`plugo-window ${position}`} ref={windowRef} role="dialog" aria-modal="true">
      <div class="plugo-header">
        <h3>{getWidgetString("chatTitle", lang)}</h3>
        <button onClick={onClose} aria-label="Close">&times;</button>
      </div>

      {/* Connection status banner */}
      {connectionState === "connecting" && (
        <div class="plugo-status-bar connecting">{getWidgetString("connecting", lang)}</div>
      )}
      {connectionState === "reconnecting" && (
        <div class="plugo-status-bar reconnecting">{getWidgetString("reconnecting", lang)}</div>
      )}
      {connectionState === "disconnected" && (
        <div class="plugo-status-bar disconnected">{getWidgetString("disconnected", lang)}</div>
      )}

      <div
        class="plugo-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Chat messages"
      >
        {messages.map((msg, i) => {
          const msgIsError = msg.role === "bot" && msg.content.startsWith("\u26a0\ufe0f");
          return (
            <Message
              key={i}
              role={msg.role}
              content={msg.content}
              timestamp={msg.timestamp}
              index={i}
              isError={msgIsError}
              onFeedback={msg.role === "bot" && msg.content && !msgIsError ? onFeedback : undefined}
              onRetry={msgIsError && onRetry ? () => onRetry(i) : undefined}
            />
          );
        })}
        {isTyping && (
          <div class="plugo-typing">
            <span />
            <span />
            <span />
            <span class="plugo-typing-text">{getWidgetString("typing", lang)}</span>
          </div>
        )}

        {/* Suggestion buttons */}
        {suggestions.length > 0 && !isTyping && (
          <div class="plugo-suggestions">
            <span class="plugo-suggestions-label">{getWidgetString("suggestions", lang)}</span>
            <div class="plugo-suggestions-list">
              {suggestions.slice(0, 4).map((s, i) => (
                <button
                  key={i}
                  class="plugo-suggestion-btn"
                  onClick={() => onSend(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* New message indicator when scrolled up */}
      {userScrolledUp && newMessageCount > 0 && (
        <button class="plugo-new-msg-btn" onClick={jumpToBottom}>
          ↓ {getWidgetString("newMessages", lang)} ({newMessageCount})
        </button>
      )}

      <form class="plugo-input-area" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onInput={handleInput}
          placeholder={getWidgetString("placeholder", lang)}
          disabled={isTyping || isOffline}
          maxLength={MAX_INPUT_LENGTH}
        />
        <button type="submit" disabled={!input.trim() || isTyping || isOffline} aria-label={getWidgetString("send", lang)}>
          {getWidgetString("send", lang)}
        </button>
      </form>
      {/* Character counter */}
      {input.length > MAX_INPUT_LENGTH * 0.6 && (
        <div class={`plugo-char-counter${input.length > MAX_INPUT_LENGTH * 0.95 ? " danger" : input.length > MAX_INPUT_LENGTH * 0.8 ? " warning" : ""}`}>
          {input.length}/{MAX_INPUT_LENGTH}
        </div>
      )}
    </div>
  );
}
