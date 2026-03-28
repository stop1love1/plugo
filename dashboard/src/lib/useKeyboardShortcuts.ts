import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

export function useKeyboardShortcuts() {
  const navigate = useNavigate();
  const { siteId } = useParams();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") {
        return;
      }

      const isCtrl = e.ctrlKey || e.metaKey;

      // Ctrl+K — Quick search (focus first search input on page)
      if (isCtrl && e.key === "k") {
        e.preventDefault();
        const searchInput = document.querySelector<HTMLInputElement>('input[type="text"], input[placeholder*="earch"]');
        if (searchInput) searchInput.focus();
      }

      // G then S — Go to Sites
      // G then A — Go to Analytics
      // etc. — using single-key navigation when no modifier
      if (!isCtrl && !e.altKey && !e.shiftKey) {
        if (!siteId) return;
        const prefix = `/site/${siteId}`;
        switch (e.key) {
          case "1": navigate(`${prefix}/analytics`); break;
          case "2": navigate(`${prefix}/setup`); break;
          case "3": navigate(`${prefix}/knowledge`); break;
          case "4": navigate(`${prefix}/tools`); break;
          case "5": navigate(`${prefix}/embed`); break;
          case "6": navigate(`${prefix}/chat-log`); break;
          case "7": navigate(`${prefix}/visitors`); break;
          case "8": navigate(`${prefix}/settings`); break;
        }
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate, siteId]);
}
