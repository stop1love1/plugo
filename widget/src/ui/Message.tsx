import { h } from "preact";
import { useMemo, useState } from "preact/hooks";
import { parseMarkdown } from "../lib/markdown";

type MessageProps = {
  role: "user" | "bot";
  content: string;
  index?: number;
  isError?: boolean;
  onFeedback?: (index: number, rating: "up" | "down") => void;
};

export function Message({ role, content, index, isError, onFeedback }: MessageProps) {
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

  // Error messages get special styling
  if (isError) {
    return <div class="plugo-msg bot plugo-error">{content}</div>;
  }

  if (role === "bot" && html) {
    return (
      <div class="plugo-msg-wrapper bot">
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
      </div>
    );
  }

  return <div class={`plugo-msg user`}>{content}</div>;
}
