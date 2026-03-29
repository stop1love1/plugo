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
      widgetTitle?: string;
      botAvatar?: string;
      headerSubtitle?: string;
      inputPlaceholder?: string;
      autoOpenDelay?: number;
      bubbleSize?: string;
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
  // Auto-detect dark mode from system preference if not explicitly set
  const darkMediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
  const isDark = config.darkMode ?? darkMediaQuery?.matches;
  if (isDark) {
    container.classList.add("plugo-dark");
  }

  // Listen for dark mode changes when not explicitly configured
  if (config.darkMode === undefined && darkMediaQuery) {
    darkMediaQuery.addEventListener("change", (e) => {
      container.classList.toggle("plugo-dark", e.matches);
    });
  }
  shadow.appendChild(container);

  render(
    h(App, {
      token: config.token,
      serverUrl: config.serverUrl || "",
      primaryColor: config.primaryColor || "#6366f1",
      greeting: config.greeting || "",
      position: config.position || "bottom-right",
      widgetTitle: config.widgetTitle || "",
      botAvatar: config.botAvatar || "",
      headerSubtitle: config.headerSubtitle || "",
      inputPlaceholder: config.inputPlaceholder || "",
      autoOpenDelay: config.autoOpenDelay || 0,
      bubbleSize: config.bubbleSize || "medium",
      getPageContext,
    }),
    container
  );
}

/** Calculate relative luminance and choose black or white text */
function getContrastTextColor(hex: string): string {
  const c = hex.replace("#", "");
  const r = parseInt(c.substring(0, 2), 16) / 255;
  const g = parseInt(c.substring(2, 4), 16) / 255;
  const b = parseInt(c.substring(4, 6), 16) / 255;
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.5 ? "#000000" : "#ffffff";
}

function getWidgetStyles(primaryColor: string): string {
  const textOnPrimary = getContrastTextColor(primaryColor);
  return `
    * { margin: 0; padding: 0; box-sizing: border-box; }

    :host {
      --plugo-primary: ${primaryColor};
      --plugo-text-on-primary: ${textOnPrimary};
      --plugo-font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --plugo-radius: 16px;
      --plugo-window-w: 380px;
      --plugo-window-h: 550px;
    }

    .plugo-bubble {
      position: fixed;
      bottom: 20px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${primaryColor}, ${primaryColor}cc);
      color: var(--plugo-text-on-primary);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 16px ${primaryColor}35, 0 2px 6px rgba(0,0,0,0.12);
      z-index: 999999;
      transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s;
      font-family: var(--plugo-font);
    }
    .plugo-bubble:hover {
      transform: scale(1.08);
      box-shadow: 0 6px 24px ${primaryColor}45, 0 4px 10px rgba(0,0,0,0.18);
    }
    .plugo-bubble:active { transform: scale(0.95); }
    .plugo-bubble.bottom-right { right: 20px; }
    .plugo-bubble.bottom-left { left: 20px; }

    /* Bubble icon transitions */
    .plugo-bubble-icon {
      position: absolute;
      width: 26px;
      height: 26px;
      transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.25s;
    }
    .plugo-bubble-chat { opacity: 1; transform: scale(1) rotate(0deg); }
    .plugo-bubble-close { opacity: 0; transform: scale(0.5) rotate(-90deg); }
    .plugo-bubble.open {
      opacity: 0;
      pointer-events: none;
      transform: scale(0.5);
    }

    .plugo-window {
      position: fixed;
      bottom: 20px;
      width: var(--plugo-window-w);
      height: var(--plugo-window-h);
      background: white;
      border-radius: var(--plugo-radius);
      box-shadow: 0 8px 40px rgba(0,0,0,0.15);
      z-index: 999998;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      font-family: var(--plugo-font);
      animation: plugo-slide-up 0.3s ease-out;
    }
    .plugo-window.bottom-right { right: 20px; }
    .plugo-window.bottom-left { left: 20px; }

    @keyframes plugo-slide-up {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .plugo-header {
      background: linear-gradient(135deg, ${primaryColor}, ${primaryColor}dd);
      color: var(--plugo-text-on-primary);
      padding: 12px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .plugo-header-left {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .plugo-header-avatar {
      width: 36px; height: 36px;
      border-radius: 50%;
      background: rgba(255,255,255,0.2);
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; flex-shrink: 0;
      backdrop-filter: blur(4px);
    }
    .plugo-header-info { min-width: 0; }
    .plugo-header h3 { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.3; }
    .plugo-header-status {
      font-size: 12px; opacity: 0.85;
      display: flex; align-items: center; gap: 5px; margin-top: 1px;
    }
    .plugo-header-status-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: #4ade80; display: inline-block;
    }
    .plugo-header-status-dot.online {
      box-shadow: 0 0 0 2px rgba(74, 222, 128, 0.3);
    }
    .plugo-header-actions { display: flex; gap: 2px; }
    .plugo-header button {
      background: rgba(255,255,255,0.12); border: none; color: inherit; cursor: pointer;
      font-size: 18px; padding: 6px; line-height: 1; border-radius: 8px;
      transition: background 0.2s;
    }
    .plugo-header button:hover { background: rgba(255,255,255,0.22); }

    .plugo-messages {
      flex: 1;
      overflow-y: auto;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .plugo-messages::-webkit-scrollbar { width: 4px; }
    .plugo-messages::-webkit-scrollbar-thumb { background: #ddd; border-radius: 4px; }

    .plugo-msg {
      padding: 8px 12px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.5;
      word-wrap: break-word;
      white-space: pre-wrap;
      animation: plugo-msg-in 0.2s ease-out;
    }
    @keyframes plugo-msg-in {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .plugo-msg.user {
      background: var(--plugo-primary);
      color: var(--plugo-text-on-primary);
      border-bottom-right-radius: 4px;
    }
    .plugo-msg.bot {
      background: #f2f3f7;
      color: #1a1a1a;
      border-bottom-left-radius: 4px;
    }

    .plugo-typing {
      padding: 10px 14px;
      background: #f2f3f7;
      border-radius: 14px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .plugo-typing span {
      width: 6px; height: 6px;
      background: #aaa;
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
      padding: 12px 12px 14px;
      border-top: 1px solid #f0f0f0;
      display: flex;
      gap: 8px;
      align-items: flex-end;
      background: #fafafa;
    }
    .plugo-input-area input,
    .plugo-input-area textarea {
      flex: 1;
      border: 1px solid #e0e0e0;
      border-radius: 20px;
      padding: 10px 16px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      font-family: inherit;
      background: #fff;
      resize: none;
    }
    .plugo-input-area input:focus,
    .plugo-input-area textarea:focus {
      border-color: var(--plugo-primary);
      box-shadow: 0 0 0 3px ${primaryColor}15;
    }
    .plugo-input-area button {
      background: var(--plugo-primary);
      color: var(--plugo-text-on-primary);
      border: none;
      border-radius: 50%;
      width: 38px; height: 38px;
      cursor: pointer;
      font-size: 14px;
      transition: opacity 0.2s, transform 0.15s;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .plugo-input-area button:hover { opacity: 0.9; transform: scale(1.05); }
    .plugo-input-area button:active { transform: scale(0.92); }
    .plugo-input-area button:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }
    .plugo-input-area button svg { width: 17px; height: 17px; }

    .plugo-suggestion-btn {
      background: white;
      border: 1px solid #e8e8ec;
      border-radius: 18px;
      padding: 7px 14px;
      font-size: 12.5px;
      cursor: pointer;
      transition: all 0.2s;
      font-family: inherit;
      color: #555;
      white-space: nowrap;
    }
    .plugo-suggestion-btn:hover {
      background: ${primaryColor}0a;
      border-color: var(--plugo-primary);
      color: var(--plugo-primary);
      transform: translateY(-1px);
      box-shadow: 0 2px 8px ${primaryColor}15;
    }

    @media (max-width: 480px) {
      .plugo-window {
        width: 100vw;
        height: 100dvh;
        bottom: 0;
        right: 0 !important;
        left: 0 !important;
        border-radius: 0;
        animation: plugo-slide-up-mobile 0.25s ease-out;
      }
      @keyframes plugo-slide-up-mobile {
        from { opacity: 0; transform: translateY(100%); }
        to { opacity: 1; transform: translateY(0); }
      }
      .plugo-bubble { bottom: 16px; }
      .plugo-bubble.bottom-right { right: 16px; }
      .plugo-bubble.bottom-left { left: 16px; }
      /* Header — larger touch targets */
      .plugo-header {
        padding: 14px 16px;
        padding-top: max(14px, env(safe-area-inset-top, 14px));
      }
      .plugo-header-avatar { width: 38px; height: 38px; font-size: 20px; }
      .plugo-header h3 { font-size: 16px; }
      .plugo-header-status { font-size: 12px; }
      .plugo-header button {
        min-width: 36px; min-height: 36px;
        font-size: 20px; padding: 8px; border-radius: 10px;
      }
      /* Messages — comfortable reading */
      .plugo-messages { padding: 14px 12px; gap: 8px; }
      .plugo-msg { font-size: 14.5px; padding: 10px 14px; border-radius: 16px; }
      .plugo-msg-wrapper.user, .plugo-msg-wrapper.bot { max-width: 90%; }
      /* Input — larger touch area, safe area */
      .plugo-input-area {
        padding: 10px 12px;
        padding-bottom: max(14px, env(safe-area-inset-bottom, 14px));
        gap: 10px;
      }
      .plugo-input-area textarea {
        font-size: 16px; /* prevent iOS zoom on focus */
        padding: 11px 16px;
        border-radius: 22px;
      }
      .plugo-input-area button {
        width: 44px; height: 44px; /* Apple's min touch target */
      }
      .plugo-input-area button svg { width: 20px; height: 20px; }
      /* Suggestions — scrollable row */
      .plugo-suggestions-list {
        flex-wrap: nowrap;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        padding-bottom: 2px;
      }
      .plugo-suggestions-list::-webkit-scrollbar { display: none; }
      .plugo-suggestion-btn { flex-shrink: 0; padding: 8px 16px; font-size: 13px; }
      /* Actions — always visible on mobile (no hover) */
      .plugo-actions { opacity: 1; }
      .plugo-action-btn { padding: 5px 8px; }
      /* Typing */
      .plugo-typing { padding: 10px 16px; }
      /* New message button */
      .plugo-new-msg-btn { bottom: 75px; padding: 8px 18px; font-size: 12px; }
      /* Slideshow */
      .plugo-slide-prev, .plugo-slide-next { width: 32px; height: 32px; font-size: 18px; }
      /* Character counter */
      .plugo-char-counter { padding-right: 12px; }
    }

    /* Markdown styles */
    .plugo-markdown p { margin: 0 0 4px 0; }
    .plugo-markdown p:last-child { margin-bottom: 0; }
    .plugo-markdown > *:first-child { margin-top: 0; }
    .plugo-markdown strong { font-weight: 600; }
    .plugo-markdown em { font-style: italic; }
    .plugo-markdown a { color: #4f46e5; text-decoration: underline; }
    .plugo-markdown a:hover { color: #3730a3; }

    /* Rich content — Images */
    .plugo-image { margin: 6px 0; border-radius: 8px; overflow: hidden; }
    .plugo-image img { width: 100%; height: auto; display: block; border-radius: 8px; cursor: pointer; }
    .plugo-image img:hover { opacity: 0.92; }

    /* Rich content — Video */
    .plugo-video { margin: 6px 0; border-radius: 8px; overflow: hidden; }
    .plugo-video iframe, .plugo-video video { width: 100%; aspect-ratio: 16/9; display: block; border-radius: 8px; }

    /* Rich content — Buttons */
    .plugo-btn {
      display: inline-flex; align-items: center; gap: 4px;
      background: var(--plugo-primary); color: var(--plugo-text-on-primary) !important;
      padding: 6px 14px; border-radius: 8px; font-size: 12.5px; font-weight: 500;
      text-decoration: none !important; transition: opacity 0.15s;
    }
    .plugo-btn:hover { opacity: 0.88; text-decoration: none !important; }
    .plugo-btn-group { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }

    /* Rich content — Slideshow */
    .plugo-slideshow { margin: 6px 0; position: relative; }
    .plugo-slide { display: none; }
    .plugo-slide.active { display: block; }
    .plugo-slide .plugo-image { margin: 0; }
    .plugo-slide-nav {
      display: flex; align-items: center; justify-content: center; gap: 8px;
      padding: 6px 0 2px;
    }
    .plugo-slide-prev, .plugo-slide-next {
      background: #e8e8ec; border: none; border-radius: 50%;
      width: 26px; height: 26px; font-size: 16px; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      color: #555; transition: background 0.15s;
    }
    .plugo-slide-prev:hover, .plugo-slide-next:hover { background: #ddd; }
    .plugo-slide-count { font-size: 11px; color: #999; min-width: 30px; text-align: center; }

    /* Dark mode — rich content */
    .plugo-dark .plugo-btn { background: var(--plugo-primary); }
    .plugo-dark .plugo-slide-prev, .plugo-dark .plugo-slide-next { background: #3d3d5c; color: #ccc; }
    .plugo-dark .plugo-slide-prev:hover, .plugo-dark .plugo-slide-next:hover { background: #4d4d6c; }
    .plugo-dark .plugo-slide-count { color: #666; }
    .plugo-markdown ul, .plugo-markdown ol { margin: 2px 0 4px 0; padding-left: 18px; }
    .plugo-markdown li { margin: 1px 0; }
    .plugo-markdown li p { margin: 0; }
    .plugo-markdown h1, .plugo-markdown h2, .plugo-markdown h3, .plugo-markdown h4 {
      font-weight: 600; margin: 4px 0 2px 0;
    }
    .plugo-markdown h1 { font-size: 1.15em; }
    .plugo-markdown h2 { font-size: 1.1em; }
    .plugo-markdown h3 { font-size: 1.05em; }
    .plugo-markdown code {
      background: #e8e8e8; padding: 1px 4px; border-radius: 3px;
      font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.85em;
    }
    .plugo-markdown pre.plugo-code {
      background: #1e1e2e; color: #cdd6f4; padding: 10px; border-radius: 8px;
      overflow-x: auto; margin: 4px 0; font-size: 0.82em; line-height: 1.45;
      position: relative;
    }
    .plugo-markdown pre.plugo-code code {
      background: none; padding: 0; color: inherit; font-size: inherit;
    }
    .plugo-markdown blockquote {
      margin: 3px 0; padding: 2px 0 2px 10px;
      border-left: 3px solid #d0d7de; color: #666;
    }
    .plugo-markdown hr { border: none; border-top: 1px solid #e0e0e0; margin: 6px 0; }
    /* Tables */
    .plugo-markdown table {
      width: 100%; border-collapse: collapse; margin: 4px 0;
      font-size: 0.9em;
    }
    .plugo-markdown th, .plugo-markdown td {
      padding: 4px 8px; border: 1px solid #e0e0e5;
      text-align: left;
    }
    .plugo-markdown th {
      background: #f5f5f8; font-weight: 600; font-size: 0.85em;
    }
    .plugo-markdown tr:nth-child(even) { background: #fafafc; }
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
    .plugo-dark .plugo-messages { background: #1a1a2e; }
    .plugo-dark .plugo-msg.bot { background: #2d2d44; color: #e0e0e0; }
    .plugo-dark .plugo-msg.user { color: #fff; }
    .plugo-dark .plugo-input-area { background: #1a1a2e; border-top-color: #2d2d44; }
    .plugo-dark .plugo-input-area input {
      background: #2d2d44; color: #e0e0e0;
      border-color: #3d3d5c;
    }
    .plugo-dark .plugo-input-area input::placeholder { color: #888; }
    .plugo-dark .plugo-input-area input:focus {
      border-color: var(--plugo-primary);
      box-shadow: 0 0 0 2px ${primaryColor}20;
    }
    .plugo-dark .plugo-typing { background: #2d2d44; }
    .plugo-dark .plugo-typing span { background: #888; }
    .plugo-dark .plugo-suggestion-btn {
      background: #2d2d44; color: #ccc;
      border-color: #3d3d5c;
    }
    .plugo-dark .plugo-suggestion-btn:hover { background: #3d3d5c; border-color: var(--plugo-primary); }
    /* Message wrapper */
    .plugo-msg-wrapper {
      display: flex;
      flex-direction: column;
      position: relative;
    }
    .plugo-msg-wrapper.user {
      max-width: 88%;
    }
    .plugo-msg-wrapper.bot {
      max-width: 88%;
    }
    /* Action bar — copy, like, dislike, retry */
    .plugo-actions {
      display: flex;
      gap: 1px;
      margin-top: 2px;
      opacity: 0;
      transition: opacity 0.15s;
    }
    .plugo-msg-row:hover .plugo-actions,
    .plugo-actions.has-feedback {
      opacity: 1;
    }
    .plugo-action-btn {
      background: transparent;
      border: none;
      border-radius: 5px;
      cursor: pointer;
      padding: 3px 5px;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s, color 0.15s;
      color: #b0b0b0;
    }
    .plugo-action-btn:hover {
      background: #ececec;
      color: #555;
    }
    .plugo-action-btn.active {
      color: var(--plugo-primary);
    }
    .plugo-dark .plugo-action-btn { color: #555; }
    .plugo-dark .plugo-action-btn:hover { background: #3d3d5c; color: #aaa; }
    .plugo-dark .plugo-action-btn.active { color: var(--plugo-primary); }

    /* Connection status bar */
    .plugo-status-bar {
      padding: 6px 16px;
      text-align: center;
      font-size: 12px;
      font-weight: 500;
      animation: plugo-slide-down 0.2s ease;
    }
    .plugo-status-bar.connecting { background: #dbeafe; color: #1e40af; }
    .plugo-status-bar.reconnecting { background: #fef3c7; color: #92400e; }
    .plugo-status-bar.disconnected { background: #fee2e2; color: #991b1b; }
    @keyframes plugo-slide-down {
      from { max-height: 0; padding: 0 16px; opacity: 0; }
      to { max-height: 40px; opacity: 1; }
    }

    /* Error messages */
    .plugo-msg.plugo-error {
      background: #fef2f2;
      color: #991b1b;
      border: 1px solid #fecaca;
      border-bottom-left-radius: 4px;
    }

    /* New message indicator */
    .plugo-new-msg-btn {
      position: absolute;
      bottom: 65px;
      left: 50%;
      transform: translateX(-50%);
      background: var(--plugo-primary);
      color: var(--plugo-text-on-primary);
      border: none;
      border-radius: 16px;
      padding: 5px 14px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      z-index: 1;
      animation: plugo-slide-up 0.2s ease;
      font-family: inherit;
    }
    .plugo-new-msg-btn:hover { opacity: 0.9; }

    /* Character counter */
    .plugo-char-counter {
      text-align: right;
      padding: 0 16px 4px;
      font-size: 10px;
      color: #999;
    }

    /* Suggestion label */
    .plugo-suggestions {
      padding: 8px 0 0;
    }
    .plugo-suggestions-label {
      font-size: 11px;
      color: #999;
      display: block;
      margin-bottom: 4px;
    }
    .plugo-suggestions-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    /* Timestamp */
    .plugo-msg-time { font-size: 10px; color: #aaa; margin-top: 2px; padding-left: 2px; }
    .plugo-dark .plugo-msg-time { color: #666; }


    /* Retry button */
    .plugo-retry-btn {
      margin-top: 6px; padding: 4px 12px;
      background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;
      border-radius: 6px; cursor: pointer; font-size: 12px;
      font-family: inherit; display: inline-flex; align-items: center;
    }
    .plugo-retry-btn:hover { background: #fecaca; }
    .plugo-dark .plugo-retry-btn { background: #3d2020; color: #fca5a5; border-color: #5c2d2d; }

    /* Streaming — smooth rendering */
    .plugo-msg.bot.streaming {
      min-height: 20px;
    }
    .plugo-msg.bot.streaming::after {
      content: "";
      display: inline-block;
      width: 2px;
      height: 1em;
      background: var(--plugo-primary);
      margin-left: 1px;
      vertical-align: text-bottom;
      animation: plugo-blink 0.7s step-end infinite;
    }
    .plugo-msg.bot.streaming p,
    .plugo-msg.bot.streaming li,
    .plugo-msg.bot.streaming pre {
      animation: none;
    }
    @keyframes plugo-blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    /* Complete dark mode */
    .plugo-dark .plugo-error { background: #3d2020; color: #fca5a5; border-color: #5c2d2d; }
    .plugo-dark .plugo-markdown a { color: #93c5fd; }
    .plugo-dark .plugo-markdown code { background: #3d3d5c; color: #e0e0e0; }
    .plugo-dark .plugo-markdown pre { background: #2d2d44; }
    .plugo-dark .plugo-markdown blockquote { border-left-color: #3d3d5c; color: #aaa; }
    .plugo-dark .plugo-markdown th { background: #2d2d44; }
    .plugo-dark .plugo-markdown th, .plugo-dark .plugo-markdown td { border-color: #3d3d5c; }
    .plugo-dark .plugo-markdown tr:nth-child(even) { background: #252540; }
    .plugo-dark .plugo-status-bar.connecting { background: #1e293b; color: #60a5fa; }
    .plugo-dark .plugo-status-bar.reconnecting { background: #1e293b; color: #fbbf24; }
    .plugo-dark .plugo-status-bar.disconnected { background: #1e293b; color: #f87171; }

    /* Character counter warning/danger */
    .plugo-char-counter.warning { color: #f59e0b; }
    .plugo-char-counter.danger { color: #ef4444; font-weight: 600; }

    /* Accessibility */
    .plugo-messages { -webkit-overflow-scrolling: touch; }
    *:focus-visible { outline: 2px solid var(--plugo-primary); outline-offset: 2px; }

    .plugo-msg-row {
      display: flex; align-items: flex-end;
    }
    .plugo-msg-row.bot { justify-content: flex-start; }
    .plugo-msg-row.user { justify-content: flex-end; }

    /* Tool call card */
    .plugo-tool-card {
      display: flex; align-items: center; gap: 10px;
      background: #f8fafc; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 10px 14px;
      font-size: 13px; color: #475569;
      animation: plugo-msg-in 0.25s ease-out;
    }
    .plugo-tool-card-icon {
      width: 28px; height: 28px; border-radius: 8px;
      background: var(--plugo-primary);
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .plugo-tool-card-icon svg { width: 14px; height: 14px; stroke: var(--plugo-text-on-primary); fill: none; }
    .plugo-tool-card-info { flex: 1; min-width: 0; }
    .plugo-tool-card-name { font-weight: 600; font-size: 12px; color: #1e293b; }
    .plugo-tool-card-status { font-size: 11px; color: #94a3b8; margin-top: 1px; }
    .plugo-tool-card .plugo-spinner {
      width: 14px; height: 14px; border: 2px solid #e2e8f0;
      border-top-color: var(--plugo-primary);
      border-radius: 50%; animation: plugo-spin 0.8s linear infinite;
    }
    @keyframes plugo-spin {
      to { transform: rotate(360deg); }
    }
    .plugo-dark .plugo-tool-card { background: #2d2d44; border-color: #3d3d5c; color: #94a3b8; }
    .plugo-dark .plugo-tool-card-name { color: #e0e0e0; }

    /* Status dot pulse */
    .plugo-header-status-dot.online {
      animation: plugo-pulse 2s infinite;
    }
    @keyframes plugo-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.6); }
      50% { box-shadow: 0 0 0 4px rgba(74, 222, 128, 0); }
    }

    /* Textarea input */
    .plugo-input-area textarea {
      flex: 1;
      border: 1px solid #ddd;
      border-radius: 16px;
      padding: 10px 16px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      font-family: inherit;
      resize: none;
      line-height: 1.4;
      max-height: 100px;
      overflow-y: auto;
    }
    .plugo-input-area textarea:focus {
      border-color: var(--plugo-primary);
      box-shadow: 0 0 0 2px ${primaryColor}20;
    }
    .plugo-dark .plugo-input-area textarea {
      background: #2d2d44; color: #e0e0e0; border-color: #3d3d5c;
    }
    .plugo-dark .plugo-input-area textarea::placeholder { color: #888; }
    .plugo-dark .plugo-input-area textarea:focus {
      border-color: var(--plugo-primary);
      box-shadow: 0 0 0 2px ${primaryColor}20;
    }
  `;
}

// Auto-init when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
