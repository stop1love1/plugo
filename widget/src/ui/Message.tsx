import { h } from "preact";

type MessageProps = {
  role: "user" | "bot";
  content: string;
};

export function Message({ role, content }: MessageProps) {
  if (!content) return null;

  return (
    <div class={`plugo-msg ${role === "user" ? "user" : "bot"}`}>
      {content}
    </div>
  );
}
