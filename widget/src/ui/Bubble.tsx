import { h } from "preact";

type BubbleProps = {
  position: "bottom-right" | "bottom-left";
  isOpen: boolean;
  onClick: () => void;
};

export function Bubble({ position, isOpen, onClick }: BubbleProps) {
  return (
    <button class={`plugo-bubble ${position}`} onClick={onClick} aria-label={isOpen ? "Close chat" : "Open chat"}>
      {isOpen ? (
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M18 6L6 18M6 6l12 12" stroke="white" stroke-width="2" stroke-linecap="round" fill="none" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"
            stroke="white"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            fill="none"
          />
        </svg>
      )}
    </button>
  );
}
