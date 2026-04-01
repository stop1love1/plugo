import { useState, useRef, useEffect, useCallback } from "preact/hooks";
import { Message } from "./Message";
import { getWidgetString, detectLanguage } from "../i18n";
import type { ConnectionState } from "../websocket";

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
  widgetTitle?: string;
  botAvatar?: string;
  headerSubtitle?: string;
  inputPlaceholder?: string;
  onSend: (message: string) => void;
  onClose: () => void;
  onMinimize?: () => void;
  onFeedback?: (index: number, rating: "up" | "down") => void;
  onRetry?: (errorIndex: number) => void;
};

export function ChatWindow({ messages, isTyping, position, suggestions, connectionState, widgetTitle, botAvatar, headerSubtitle, inputPlaceholder, onSend, onClose, onMinimize, onFeedback, onRetry }: WindowProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const windowRef = useRef<HTMLDivElement>(null);
  const [lang] = useState(() => detectLanguage());
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const [newMessageCount, setNewMessageCount] = useState(0);

  const isOffline = connectionState === "disconnected" || connectionState === "reconnecting";
  const prevMsgCountRef = useRef(messages.length);

  // Smart auto-scroll: only scroll if user is near bottom
  useEffect(() => {
    const msgCountChanged = messages.length !== prevMsgCountRef.current;
    prevMsgCountRef.current = messages.length;

    if (!userScrolledUp) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    } else if (msgCountChanged && messages.length > 0) {
      // Only count genuinely new messages, not token updates
      setNewMessageCount((c) => c + 1);
    }
  }, [messages, isTyping, userScrolledUp]);

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

  // Focus textarea when opened
  useEffect(() => {
    textareaRef.current?.focus();
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
      if (e.key !== "Tab") return;
      const focusable = windowRef.current?.querySelectorAll<HTMLElement>(
        'button, textarea, [tabindex]:not([tabindex="-1"])'
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
    document.addEventListener("keydown", handleTab);
    return () => document.removeEventListener("keydown", handleTab);
  }, []);

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    if (!input.trim() || isTyping || isOffline) return;
    onSend(input.trim());
    setInput("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    // Enter sends, Shift+Enter adds newline
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInput = (e: Event) => {
    const el = e.target as HTMLTextAreaElement;
    const val = el.value;
    if (val.length <= MAX_INPUT_LENGTH) {
      setInput(val);
    }
    // Auto-resize textarea
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 100) + "px";
  };

  // Determine message grouping
  const isLastInGroup = (i: number) => {
    if (i >= messages.length - 1) return true;
    return messages[i].role !== messages[i + 1].role;
  };

  return (
    <div class={`plugo-window ${position}`} ref={windowRef} role="dialog" aria-modal="true">
      <div class="plugo-header">
        <div class="plugo-header-left">
          <div class="plugo-header-avatar">{botAvatar || "\u{1F4AC}"}</div>
          <div class="plugo-header-info">
            <h3>{widgetTitle || getWidgetString("chatTitle", lang)}</h3>
            <div class="plugo-header-status">
              <span
                class={`plugo-header-status-dot${connectionState === "connected" ? " online" : ""}`}
                style={connectionState !== "connected" ? "background:#f59e0b" : ""}
              />
              {headerSubtitle ||
                (connectionState === "connected"
                  ? "Online"
                  : getWidgetString(
                      connectionState as "connecting" | "reconnecting" | "disconnected",
                      lang
                    ))}
            </div>
          </div>
        </div>
        <div class="plugo-header-actions">
          {onMinimize && (
            <button onClick={onMinimize} aria-label="Minimize" title="Minimize">&minus;</button>
          )}
          <button onClick={onClose} aria-label="Close" title="Close">&times;</button>
        </div>
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
              key={`${msg.role}-${msg.timestamp}-${i}`}
              role={msg.role}
              content={msg.content}
              timestamp={msg.timestamp}
              index={i}
              isError={msgIsError}
              isStreaming={isTyping && i === messages.length - 1 && msg.role === "bot" && !msgIsError}
              isLastInGroup={isLastInGroup(i)}
              onFeedback={msg.role === "bot" && msg.content && !msgIsError && !isTyping ? onFeedback : undefined}
              onRetry={msg.role === "bot" && msg.content && onRetry && !isTyping ? () => onRetry(i) : undefined}
            />
          );
        })}
        {isTyping && !(messages.length > 0 && messages[messages.length - 1].role === "bot" && messages[messages.length - 1].content) && (
          <div class="plugo-msg-row bot">
            <div class="plugo-typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {/* Suggestion buttons — only show when no conversation yet (just greeting) */}
        {suggestions.length > 0 && !isTyping && messages.length <= 1 && (
          <div class="plugo-suggestions">
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
          {"\u2193"} {getWidgetString("newMessages", lang)} ({newMessageCount})
        </button>
      )}

      <form class="plugo-input-area" onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          value={input}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={inputPlaceholder || getWidgetString("placeholder", lang)}
          disabled={isTyping || isOffline}
          maxLength={MAX_INPUT_LENGTH}
          rows={1}
        />
        <button type="submit" disabled={!input.trim() || isTyping || isOffline} aria-label={getWidgetString("send", lang)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
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
