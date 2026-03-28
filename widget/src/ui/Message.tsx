import { h } from "preact";
import { useMemo, useState } from "preact/hooks";
import { parseMarkdown } from "../lib/markdown";

type MessageProps = {
  role: "user" | "bot";
  content: string;
  timestamp?: number;
  index?: number;
  isError?: boolean;
  onFeedback?: (index: number, rating: "up" | "down") => void;
  onRetry?: () => void;
};

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <button class="plugo-copy-btn" onClick={handleCopy} aria-label="Copy message" title={copied ? "Copied!" : "Copy"}>
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

export function Message({ role, content, timestamp, index, isError, onFeedback, onRetry }: MessageProps) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  if (!content) return null;

  const html = useMemo(
    () => (role === "bot" && !isError ? parseMarkdown(content) : null),
    [role, content, isError]
  );

  const handleFeedback = (rating: "up" | "down") => {
    setFeedback(rating);
    if (onFeedback && index !== undefined) {
      onFeedback(index, rating);
    }
  };

  const timeDisplay = timestamp ? (
    <div class="plugo-msg-time">{formatTime(timestamp)}</div>
  ) : null;

  // Error messages get special styling
  if (isError) {
    return (
      <div class="plugo-msg-wrapper bot" role="article" aria-label="Bot message">
        <div class="plugo-msg bot plugo-error">{content}</div>
        {onRetry && (
          <button class="plugo-retry-btn" onClick={onRetry}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Retry
          </button>
        )}
        {timeDisplay}
      </div>
    );
  }

  if (role === "bot" && html) {
    return (
      <div class="plugo-msg-wrapper bot" role="article" aria-label="Bot message">
        <CopyButton content={content} />
        <div
          class="plugo-msg bot plugo-markdown"
          dangerouslySetInnerHTML={{ __html: html }}
        />
        {onFeedback && index !== undefined && (
          <div class="plugo-feedback">
            <button
              class={`plugo-feedback-btn ${feedback === "up" ? "active" : ""}`}
              onClick={() => handleFeedback("up")}
              aria-label="Helpful"
              title="Helpful"
            >
              &#128077;
            </button>
            <button
              class={`plugo-feedback-btn ${feedback === "down" ? "active" : ""}`}
              onClick={() => handleFeedback("down")}
              aria-label="Not helpful"
              title="Not helpful"
            >
              &#128078;
            </button>
          </div>
        )}
        {timeDisplay}
      </div>
    );
  }

  return (
    <div class="plugo-msg-wrapper" style={role === "user" ? "align-self: flex-end;" : ""} role="article" aria-label={role === "user" ? "Your message" : "Bot message"}>
      <div class={`plugo-msg user`}>{content}</div>
      {timeDisplay}
    </div>
  );
}
