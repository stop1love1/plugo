import { h } from "preact";

type BubbleProps = {
  position: "bottom-right" | "bottom-left";
  isOpen: boolean;
  unreadCount?: number;
  bubbleSize?: string;
  onClick: () => void;
};

const sizeMap: Record<string, string> = { small: "48px", medium: "56px", large: "64px" };

export function Bubble({ position, isOpen, unreadCount = 0, bubbleSize, onClick }: BubbleProps) {
  const sz = sizeMap[bubbleSize || "medium"] || "56px";
  return (
    <button
      class={`plugo-bubble ${position}${isOpen ? " open" : ""}`}
      style={`width:${sz};height:${sz}`}
      onClick={onClick}
      aria-label={isOpen ? "Close chat" : "Open chat"}
      aria-expanded={isOpen}
    >
      {/* Chat icon */}
      <svg class="plugo-bubble-icon plugo-bubble-chat" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"
          fill="currentColor" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx="9" cy="11.5" r="1" fill="white" />
        <circle cx="12.5" cy="11.5" r="1" fill="white" />
        <circle cx="16" cy="11.5" r="1" fill="white" />
      </svg>
      {/* Close icon */}
      <svg class="plugo-bubble-icon plugo-bubble-close" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
        <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
      </svg>
      {!isOpen && unreadCount > 0 && (
        <span class="plugo-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
      )}
    </button>
  );
}
