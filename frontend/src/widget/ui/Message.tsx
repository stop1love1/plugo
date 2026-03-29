import { h } from "preact";
import { useMemo, useState } from "preact/hooks";
import { parseMarkdown } from "../markdown";

export type MessageProps = {
  role: "user" | "bot";
  content: string;
  timestamp?: number;
  index?: number;
  isError?: boolean;
  isLastInGroup?: boolean;
  onFeedback?: (index: number, rating: "up" | "down") => void;
  onRetry?: () => void;
};

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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

/** Detect tool call markers in the content: "> Calling **name**..." */
function parseToolCalls(content: string): { toolName: string; isComplete: boolean } | null {
  // Match: > Calling **name**...
  const match = content.match(/^>\s*Calling \*\*(.+?)\*\*/m);
  if (match) {
    return { toolName: match[1], isComplete: false };
  }
  return null;
}

function ToolCallCard({ toolName, isComplete }: { toolName: string; isComplete: boolean }) {
  return (
    <div class="plugo-tool-card">
      <div class="plugo-tool-card-icon">
        <svg viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
      </div>
      <div class="plugo-tool-card-info">
        <div class="plugo-tool-card-name">{toolName}</div>
        <div class="plugo-tool-card-status">{isComplete ? "Completed" : "Executing..."}</div>
      </div>
      {!isComplete && <div class="plugo-spinner" />}
      {isComplete && (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </div>
  );
}

function BotAvatar() {
  return (
    <div class="plugo-avatar" aria-hidden="true">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    </div>
  );
}

export function Message({ role, content, timestamp, index, isError, isLastInGroup = true, onFeedback, onRetry }: MessageProps) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  if (!content) return null;

  // Check for tool call markers in bot content
  const toolCall = useMemo(
    () => (role === "bot" && !isError ? parseToolCalls(content) : null),
    [role, content, isError]
  );

  // Strip tool call lines from content for markdown rendering
  const cleanContent = useMemo(() => {
    if (!toolCall) return content;
    return content.replace(/^>\s*Calling \*\*.+?\*\*.*$/gm, "").trim();
  }, [content, toolCall]);

  const html = useMemo(
    () => (role === "bot" && !isError && cleanContent ? parseMarkdown(cleanContent) : null),
    [role, cleanContent, isError]
  );

  const handleFeedback = (rating: "up" | "down") => {
    setFeedback(rating);
    if (onFeedback && index !== undefined) {
      onFeedback(index, rating);
    }
  };

  const timeDisplay = isLastInGroup && timestamp ? (
    <div class="plugo-msg-time">{formatTime(timestamp)}</div>
  ) : null;

  // Error messages
  if (isError) {
    return (
      <div class="plugo-msg-row bot" role="article" aria-label="Bot message">
        <BotAvatar />
        <div class="plugo-msg-wrapper bot">
          <div class="plugo-msg bot plugo-error">{content}</div>
          {onRetry && (
            <button class="plugo-retry-btn" onClick={onRetry} aria-label="Retry">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Retry
            </button>
          )}
          {timeDisplay}
        </div>
      </div>
    );
  }

  // Bot messages with markdown
  if (role === "bot" && (html || toolCall)) {
    return (
      <div class="plugo-msg-row bot" role="article" aria-label="Bot message">
        <BotAvatar />
        <div class="plugo-msg-wrapper bot">
          {toolCall && <ToolCallCard toolName={toolCall.toolName} isComplete={!!cleanContent} />}
          {html && (
            <>
              <CopyButton content={cleanContent} />
              <div
                class="plugo-msg bot plugo-markdown"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            </>
          )}
          {onFeedback && index !== undefined && cleanContent && (
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
      </div>
    );
  }

  // User messages
  return (
    <div class={`plugo-msg-row ${role}`} role="article" aria-label={role === "user" ? "Your message" : "Bot message"}>
      <div class={`plugo-msg-wrapper ${role}`}>
        <div class={`plugo-msg ${role}`}>{content}</div>
        {timeDisplay}
      </div>
    </div>
  );
}
