import { h } from "preact";
import { useMemo } from "preact/hooks";
import { parseMarkdown } from "../lib/markdown";

type MessageProps = {
  role: "user" | "bot";
  content: string;
};

export function Message({ role, content }: MessageProps) {
  if (!content) return null;

  const html = useMemo(
    () => (role === "bot" ? parseMarkdown(content) : null),
    [role, content]
  );

  if (role === "bot" && html) {
    return (
      <div
        class="plugo-msg bot plugo-markdown"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  return <div class={`plugo-msg user`}>{content}</div>;
}
