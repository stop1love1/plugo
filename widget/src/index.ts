import { render, h } from "preact";
import { App } from "./ui/App";

declare global {
  interface Window {
    PlugoConfig?: {
      token: string;
      serverUrl?: string;
      primaryColor?: string;
      greeting?: string;
      position?: "bottom-right" | "bottom-left";
      language?: string;
      darkMode?: boolean;
    };
  }
}

function getPageContext() {
  return {
    url: window.location.href,
    title: document.title,
    meta:
      document
        .querySelector('meta[name="description"]')
        ?.getAttribute("content") || "",
    pageText: (document.body?.innerText || "").substring(0, 2000),
  };
}

function init() {
  const config = window.PlugoConfig;
  if (!config || !config.token) {
    console.warn("[Plugo] Missing config. Set window.PlugoConfig = { token: '...' }");
    return;
  }

  // Create shadow DOM container
  const host = document.createElement("div");
  host.id = "plugo-widget";
  document.body.appendChild(host);

  const shadow = host.attachShadow({ mode: "open" });

  // Inject styles into shadow DOM
  const style = document.createElement("style");
  style.textContent = getWidgetStyles(config.primaryColor || "#6366f1");
  shadow.appendChild(style);

  // Render app into shadow DOM
  const container = document.createElement("div");
  container.id = "plugo-root";
  if (config.darkMode) {
    container.classList.add("plugo-dark");
  }
  shadow.appendChild(container);

  render(
    h(App, {
      token: config.token,
      serverUrl: config.serverUrl || "",
      primaryColor: config.primaryColor || "#6366f1",
      greeting: config.greeting || "Xin chào! Tôi có thể giúp gì?",
      position: config.position || "bottom-right",
      getPageContext,
    }),
    container
  );
}

function getWidgetStyles(primaryColor: string): string {
  return `
    * { margin: 0; padding: 0; box-sizing: border-box; }

    .plugo-bubble {
      position: fixed;
      bottom: 20px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${primaryColor};
      color: white;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      z-index: 999999;
      transition: transform 0.2s, box-shadow 0.2s;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .plugo-bubble:hover { transform: scale(1.1); box-shadow: 0 6px 24px rgba(0,0,0,0.3); }
    .plugo-bubble.bottom-right { right: 20px; }
    .plugo-bubble.bottom-left { left: 20px; }
    .plugo-bubble svg { width: 28px; height: 28px; fill: white; }

    .plugo-window {
      position: fixed;
      bottom: 90px;
      width: 380px;
      height: 520px;
      background: white;
      border-radius: 16px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.15);
      z-index: 999998;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      animation: plugo-slide-up 0.3s ease-out;
    }
    .plugo-window.bottom-right { right: 20px; }
    .plugo-window.bottom-left { left: 20px; }

    @keyframes plugo-slide-up {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .plugo-header {
      background: ${primaryColor};
      color: white;
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .plugo-header h3 { font-size: 16px; font-weight: 600; }
    .plugo-header button {
      background: none; border: none; color: white; cursor: pointer;
      font-size: 20px; padding: 4px; line-height: 1;
    }

    .plugo-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .plugo-messages::-webkit-scrollbar { width: 4px; }
    .plugo-messages::-webkit-scrollbar-thumb { background: #ddd; border-radius: 4px; }

    .plugo-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.5;
      word-wrap: break-word;
      white-space: pre-wrap;
    }
    .plugo-msg.user {
      align-self: flex-end;
      background: ${primaryColor};
      color: white;
      border-bottom-right-radius: 4px;
    }
    .plugo-msg.bot {
      align-self: flex-start;
      background: #f1f3f5;
      color: #1a1a1a;
      border-bottom-left-radius: 4px;
    }

    .plugo-typing {
      align-self: flex-start;
      padding: 10px 14px;
      background: #f1f3f5;
      border-radius: 12px;
      display: flex;
      gap: 4px;
    }
    .plugo-typing span {
      width: 6px; height: 6px;
      background: #999;
      border-radius: 50%;
      animation: plugo-bounce 1.4s infinite ease-in-out;
    }
    .plugo-typing span:nth-child(2) { animation-delay: 0.2s; }
    .plugo-typing span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes plugo-bounce {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }

    .plugo-input-area {
      padding: 12px;
      border-top: 1px solid #eee;
      display: flex;
      gap: 8px;
    }
    .plugo-input-area input {
      flex: 1;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
      font-family: inherit;
    }
    .plugo-input-area input:focus { border-color: ${primaryColor}; }
    .plugo-input-area button {
      background: ${primaryColor};
      color: white;
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      cursor: pointer;
      font-size: 14px;
      transition: opacity 0.2s;
    }
    .plugo-input-area button:hover { opacity: 0.9; }
    .plugo-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }

    .plugo-suggestions {
      padding: 8px 16px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .plugo-suggestions button {
      background: #f1f3f5;
      border: 1px solid #e0e0e0;
      border-radius: 16px;
      padding: 6px 12px;
      font-size: 12px;
      cursor: pointer;
      transition: background 0.2s;
      font-family: inherit;
      color: #333;
    }
    .plugo-suggestions button:hover { background: #e2e8f0; }

    @media (max-width: 480px) {
      .plugo-window {
        width: 100vw;
        height: 100vh;
        bottom: 0;
        right: 0;
        left: 0;
        border-radius: 0;
      }
    }

    /* Markdown styles */
    .plugo-markdown p { margin: 0 0 8px 0; }
    .plugo-markdown p:last-child { margin-bottom: 0; }
    .plugo-markdown strong { font-weight: 600; }
    .plugo-markdown em { font-style: italic; }
    .plugo-markdown a { color: #4f46e5; text-decoration: underline; }
    .plugo-markdown a:hover { color: #3730a3; }
    .plugo-markdown ul, .plugo-markdown ol { margin: 4px 0 8px 0; padding-left: 20px; }
    .plugo-markdown li { margin: 2px 0; }
    .plugo-markdown h1, .plugo-markdown h2, .plugo-markdown h3, .plugo-markdown h4 {
      font-weight: 600; margin: 8px 0 4px 0;
    }
    .plugo-markdown h1 { font-size: 1.25em; }
    .plugo-markdown h2 { font-size: 1.15em; }
    .plugo-markdown h3 { font-size: 1.05em; }
    .plugo-markdown code {
      background: #e8e8e8; padding: 1px 4px; border-radius: 3px;
      font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.85em;
    }
    .plugo-markdown pre.plugo-code {
      background: #1e1e2e; color: #cdd6f4; padding: 12px; border-radius: 8px;
      overflow-x: auto; margin: 8px 0; font-size: 0.82em; line-height: 1.5;
    }
    .plugo-markdown pre.plugo-code code {
      background: none; padding: 0; color: inherit; font-size: inherit;
    }
    .plugo-markdown blockquote {
      border-left: 3px solid #d0d0d0; padding-left: 12px; margin: 8px 0;
      color: #666; font-style: italic;
    }
    .plugo-markdown hr { border: none; border-top: 1px solid #e0e0e0; margin: 12px 0; }
    /* highlight.js theme (Catppuccin-inspired) */
    .hljs-keyword, .hljs-selector-tag { color: #cba6f7; }
    .hljs-string, .hljs-attr { color: #a6e3a1; }
    .hljs-number, .hljs-literal { color: #fab387; }
    .hljs-comment { color: #6c7086; font-style: italic; }
    .hljs-built_in, .hljs-type { color: #89dceb; }
    .hljs-function .hljs-title, .hljs-title.function_ { color: #89b4fa; }
    .hljs-variable, .hljs-template-variable { color: #f38ba8; }
    .hljs-tag { color: #cba6f7; }
    .hljs-name { color: #89b4fa; }
    .hljs-attribute { color: #f9e2af; }
    .hljs-meta { color: #fab387; }
    .hljs-punctuation { color: #bac2de; }

    /* Unread badge */
    .plugo-badge {
      position: absolute; top: -4px; right: -4px;
      background: #ef4444; color: #fff;
      font-size: 11px; font-weight: 600;
      min-width: 18px; height: 18px;
      border-radius: 9px; display: flex;
      align-items: center; justify-content: center;
      padding: 0 4px; line-height: 1;
      border: 2px solid #fff;
      animation: plugo-badge-pop 0.3s ease;
    }
    @keyframes plugo-badge-pop {
      0% { transform: scale(0); }
      50% { transform: scale(1.2); }
      100% { transform: scale(1); }
    }

    /* Dark mode */
    .plugo-dark .plugo-window { background: #1a1a2e; }
    .plugo-dark .plugo-header { background: #16213e; }
    .plugo-dark .plugo-messages { background: #1a1a2e; }
    .plugo-dark .plugo-msg.bot { background: #2d2d44; color: #e0e0e0; }
    .plugo-dark .plugo-msg.user { color: #fff; }
    .plugo-dark .plugo-input-area { background: #1a1a2e; border-top-color: #2d2d44; }
    .plugo-dark .plugo-input-area input {
      background: #2d2d44; color: #e0e0e0;
      border-color: #3d3d5c;
    }
    .plugo-dark .plugo-input-area input::placeholder { color: #888; }
    .plugo-dark .plugo-typing span { background: #888; }
    .plugo-dark .plugo-suggestion-btn {
      background: #2d2d44; color: #ccc;
      border-color: #3d3d5c;
    }
    .plugo-dark .plugo-suggestion-btn:hover { background: #3d3d5c; }

    /* Accessibility */
    .plugo-messages { -webkit-overflow-scrolling: touch; }
    .plugo-bubble { position: relative; }
  `;
}

// Auto-init when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
