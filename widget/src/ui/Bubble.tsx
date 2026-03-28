import { h } from "preact";

type BubbleProps = {
  position: "bottom-right" | "bottom-left";
  isOpen: boolean;
  unreadCount?: number;
  onClick: () => void;
};

export function Bubble({ position, isOpen, unreadCount = 0, onClick }: BubbleProps) {
  return (
    <button
      class={`plugo-bubble ${position}`}
      onClick={onClick}
      aria-label={isOpen ? "Close chat" : "Open chat"}
      aria-expanded={isOpen}
    >
      {isOpen ? "\u2715" : "\u{1F4AC}"}
      {!isOpen && unreadCount > 0 && (
        <span class="plugo-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
      )}
    </button>
  );
}
