import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite } from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { Play, RotateCcw, Monitor, Smartphone, Tablet, Sun, Moon, ExternalLink } from "lucide-react";

type Device = "desktop" | "tablet" | "mobile";

const deviceStyles: Record<Device, { width: string; height: string; label: string }> = {
  desktop: { width: "100%", height: "100%", label: "Desktop" },
  tablet: { width: "768px", height: "100%", label: "Tablet" },
  mobile: { width: "375px", height: "100%", label: "Mobile" },
};

export default function Playground() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [darkMode, setDarkMode] = useState(false);
  const [demoPage, setDemoPage] = useState("landing");
  const [key, setKey] = useState(0);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const demoPages: Record<string, { title: string; content: string }> = {
    landing: {
      title: t("playground.pageLanding"),
      content: getDemoLandingPage(site, darkMode),
    },
    pricing: {
      title: t("playground.pagePricing"),
      content: getDemoPricingPage(site, darkMode),
    },
    docs: {
      title: t("playground.pageDocs"),
      content: getDemoDocsPage(site, darkMode),
    },
    blank: {
      title: t("playground.pageBlank"),
      content: getDemoBlankPage(site, darkMode),
    },
  };

  useEffect(() => {
    if (iframeRef.current && site) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(demoPages[demoPage].content);
        doc.close();
      }
    }
  }, [site, demoPage, darkMode, key]);

  const handleReload = () => setKey((k) => k + 1);

  const handleOpenExternal = () => {
    if (!site) return;
    const blob = new Blob([demoPages[demoPage].content], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  };

  if (!site) {
    return <div className="flex items-center justify-center h-64 text-gray-400">{t("common.loading")}</div>;
  }

  const deviceStyle = deviceStyles[device];

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("playground.title")}</h1>
          <p className="text-gray-500 text-sm">{t("playground.subtitle")}</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="bg-white border border-gray-200 rounded-t-xl px-4 py-2 flex items-center justify-between">
        {/* Left: Page selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-medium mr-1">{t("playground.page")}:</span>
          {Object.entries(demoPages).map(([id, page]) => (
            <button
              key={id}
              onClick={() => setDemoPage(id)}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                demoPage === id
                  ? "bg-primary-100 text-primary-700 font-medium"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              {page.title}
            </button>
          ))}
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-1">
          {/* Device selector */}
          {[
            { id: "desktop" as Device, icon: Monitor },
            { id: "tablet" as Device, icon: Tablet },
            { id: "mobile" as Device, icon: Smartphone },
          ].map(({ id, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setDevice(id)}
              className={`p-1.5 rounded transition-colors ${
                device === id ? "bg-gray-200 text-gray-800" : "text-gray-400 hover:text-gray-600"
              }`}
              title={deviceStyles[id].label}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}

          <div className="w-px h-5 bg-gray-200 mx-1" />

          {/* Dark mode */}
          <button
            onClick={() => setDarkMode(!darkMode)}
            className={`p-1.5 rounded transition-colors ${
              darkMode ? "bg-gray-700 text-yellow-400" : "text-gray-400 hover:text-gray-600"
            }`}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Reload */}
          <button
            onClick={handleReload}
            className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors"
            title={t("playground.reload")}
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {/* Open external */}
          <button
            onClick={handleOpenExternal}
            className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors"
            title={t("playground.openExternal")}
          >
            <ExternalLink className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Preview area */}
      <div className="flex-1 bg-gray-100 border border-t-0 border-gray-200 rounded-b-xl flex items-start justify-center overflow-hidden p-4">
        <div
          className="bg-white shadow-lg rounded-lg overflow-hidden transition-all duration-300 h-full"
          style={{
            width: deviceStyle.width,
            maxWidth: "100%",
          }}
        >
          <iframe
            ref={iframeRef}
            key={key}
            title="Widget Playground"
            className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups"
          />
        </div>
      </div>

      {/* Info bar */}
      <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
        <span>
          Token: <code className="bg-gray-100 px-1 rounded">{site.token?.slice(0, 12)}...</code>
        </span>
        <span className="flex items-center gap-1">
          <Play className="w-3 h-3" />
          {t("playground.liveChat")}
        </span>
      </div>
    </div>
  );
}

// --- HTML escaping for safe injection into template strings ---

const escapeHtml = (str: string) =>
  str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// --- Demo page generators ---

function getWidgetScript(site: any, darkMode: boolean): string {
  const backendUrl = import.meta.env.VITE_BACKEND_URL || '';
  const wsBackendUrl = backendUrl ? backendUrl.replace(/^http/, 'ws') : '';
  return `
<script>
  window.PlugoConfig = {
    token: ${JSON.stringify(site.token || "")},
    serverUrl: ${wsBackendUrl ? JSON.stringify(wsBackendUrl) : '"ws://" + window.location.hostname + ":" + window.location.port'},
    primaryColor: ${JSON.stringify(site.primary_color || "#6366f1")},
    greeting: ${JSON.stringify(site.greeting || "Hello! How can I help you?")},
    position: ${JSON.stringify(site.position || "bottom-right")},
    darkMode: ${darkMode}
  };
</script>
<script src="${backendUrl}/static/widget.js" async></script>`;
}

function baseStyles(dark: boolean): string {
  const bg = dark ? "#0f172a" : "#ffffff";
  const text = dark ? "#e2e8f0" : "#1e293b";
  const muted = dark ? "#94a3b8" : "#64748b";
  const card = dark ? "#1e293b" : "#f8fafc";
  const border = dark ? "#334155" : "#e2e8f0";
  return `
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: ${bg}; color: ${text}; line-height: 1.6; }
    .container { max-width: 960px; margin: 0 auto; padding: 0 24px; }
    .muted { color: ${muted}; }
    .card { background: ${card}; border: 1px solid ${border}; border-radius: 12px; padding: 24px; }
    a { color: #6366f1; text-decoration: none; }
    a:hover { text-decoration: underline; }
  `;
}

function getDemoLandingPage(site: any, dark: boolean): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - Demo</title>
<style>
  ${baseStyles(dark)}
  .hero { padding: 80px 0 60px; text-align: center; }
  .hero h1 { font-size: 2.5rem; font-weight: 800; margin-bottom: 16px; }
  .hero p { font-size: 1.1rem; max-width: 560px; margin: 0 auto 32px; }
  .btn { display: inline-block; background: ${accent}; color: #fff; padding: 12px 32px; border-radius: 8px; font-weight: 600; font-size: 1rem; }
  .btn:hover { opacity: 0.9; text-decoration: none; }
  .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; padding: 40px 0; }
  .feature h3 { margin-bottom: 8px; font-size: 1rem; }
  .feature p { font-size: 0.875rem; }
  .nav { padding: 16px 0; border-bottom: 1px solid ${dark ? "#334155" : "#e2e8f0"}; display: flex; align-items: center; justify-content: space-between; }
  .nav-brand { font-weight: 700; font-size: 1.25rem; color: ${accent}; }
  .nav-links { display: flex; gap: 24px; font-size: 0.875rem; }
  .footer { padding: 32px 0; text-align: center; font-size: 0.8rem; border-top: 1px solid ${dark ? "#334155" : "#e2e8f0"}; margin-top: 40px; }
</style></head><body>
<div class="container">
  <nav class="nav">
    <div class="nav-brand">${safeName}</div>
    <div class="nav-links">
      <a href="#">Features</a>
      <a href="#">Pricing</a>
      <a href="#">Docs</a>
      <a href="#">Contact</a>
    </div>
  </nav>
  <div class="hero">
    <h1>Welcome to ${safeName}</h1>
    <p class="muted">This is a demo website to test your Plugo chat widget. Try clicking the chat bubble in the bottom corner!</p>
    <a href="#" class="btn">Get Started</a>
  </div>
  <div class="features">
    <div class="card feature">
      <h3>AI-Powered Chat</h3>
      <p class="muted">Intelligent responses based on your website content and knowledge base.</p>
    </div>
    <div class="card feature">
      <h3>Easy Integration</h3>
      <p class="muted">Just paste a script tag — works with any website or framework.</p>
    </div>
    <div class="card feature">
      <h3>Customizable</h3>
      <p class="muted">Match your brand with custom colors, greetings, and positioning.</p>
    </div>
  </div>
  <footer class="footer muted">© 2026 ${safeName}. This is a demo page for testing the Plugo widget.</footer>
</div>
${getWidgetScript(site, dark)}
</body></html>`;
}

function getDemoPricingPage(site: any, dark: boolean): string {
  if (!site) return "";
  const accent = site.primary_color || "#6366f1";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - Pricing</title>
<style>
  ${baseStyles(dark)}
  h1 { text-align: center; padding: 60px 0 16px; font-size: 2rem; }
  .subtitle { text-align: center; margin-bottom: 40px; }
  .plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; padding-bottom: 60px; }
  .plan { text-align: center; }
  .plan h3 { font-size: 1.1rem; margin-bottom: 8px; }
  .plan .price { font-size: 2rem; font-weight: 800; color: ${accent}; margin: 12px 0; }
  .plan .price span { font-size: 0.9rem; font-weight: 400; }
  .plan ul { list-style: none; margin: 16px 0; font-size: 0.875rem; }
  .plan ul li { padding: 6px 0; }
  .plan ul li::before { content: "✓ "; color: ${accent}; font-weight: 700; }
  .plan-btn { display: inline-block; border: 2px solid ${accent}; color: ${accent}; padding: 10px 28px; border-radius: 8px; font-weight: 600; }
  .plan-btn:hover { background: ${accent}; color: #fff; text-decoration: none; }
  .popular { border-color: ${accent} !important; position: relative; }
  .popular::before { content: "Popular"; position: absolute; top: -12px; left: 50%; transform: translateX(-50%); background: ${accent}; color: #fff; padding: 2px 12px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
</style></head><body>
<div class="container">
  <h1>Pricing Plans</h1>
  <p class="subtitle muted">Choose the plan that fits your needs. Ask our chat bot for help!</p>
  <div class="plans">
    <div class="card plan">
      <h3>Starter</h3>
      <div class="price">Free<span></span></div>
      <ul><li>1 site</li><li>100 messages/mo</li><li>Basic analytics</li></ul>
      <a href="#" class="plan-btn">Get Started</a>
    </div>
    <div class="card plan popular">
      <h3>Pro</h3>
      <div class="price">$29<span>/mo</span></div>
      <ul><li>5 sites</li><li>10,000 messages/mo</li><li>Advanced analytics</li><li>Custom branding</li></ul>
      <a href="#" class="plan-btn">Start Trial</a>
    </div>
    <div class="card plan">
      <h3>Enterprise</h3>
      <div class="price">Custom</div>
      <ul><li>Unlimited sites</li><li>Unlimited messages</li><li>Dedicated support</li><li>SLA guarantee</li></ul>
      <a href="#" class="plan-btn">Contact Us</a>
    </div>
  </div>
</div>
${getWidgetScript(site, dark)}
</body></html>`;
}

function getDemoDocsPage(site: any, dark: boolean): string {
  if (!site) return "";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName} - Documentation</title>
<style>
  ${baseStyles(dark)}
  .docs { display: grid; grid-template-columns: 200px 1fr; gap: 32px; padding: 40px 0; min-height: 80vh; }
  .sidebar { font-size: 0.875rem; }
  .sidebar h4 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 8px; }
  .sidebar a { display: block; padding: 4px 0; color: ${dark ? "#94a3b8" : "#64748b"}; }
  .sidebar a:hover { color: ${dark ? "#e2e8f0" : "#1e293b"}; text-decoration: none; }
  .content h1 { font-size: 1.75rem; margin-bottom: 16px; }
  .content h2 { font-size: 1.25rem; margin: 24px 0 12px; }
  .content p { margin-bottom: 12px; font-size: 0.9375rem; }
  .content code { background: ${dark ? "#334155" : "#f1f5f9"}; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }
  .content pre { background: ${dark ? "#1a1a2e" : "#f8fafc"}; border: 1px solid ${dark ? "#334155" : "#e2e8f0"}; padding: 16px; border-radius: 8px; overflow-x: auto; margin: 12px 0; font-size: 0.85rem; }
  @media (max-width: 640px) { .docs { grid-template-columns: 1fr; } .sidebar { display: none; } }
</style></head><body>
<div class="container">
  <div class="docs">
    <nav class="sidebar">
      <h4>Getting Started</h4>
      <a href="#">Installation</a>
      <a href="#">Quick Start</a>
      <a href="#">Configuration</a>
      <h4>Features</h4>
      <a href="#">Chat Widget</a>
      <a href="#">Knowledge Base</a>
      <a href="#">API Tools</a>
      <h4>API Reference</h4>
      <a href="#">REST API</a>
      <a href="#">WebSocket</a>
    </nav>
    <div class="content">
      <h1>Getting Started</h1>
      <p>Welcome to the ${safeName} documentation. This guide will help you set up and configure your chat widget.</p>
      <h2>Installation</h2>
      <p>Add the following code to your website, just before the closing <code>&lt;/body&gt;</code> tag:</p>
      <pre>&lt;script&gt;
  window.PlugoConfig = {
    token: "${escapeHtml(site.token || "")}"
  };
&lt;/script&gt;
&lt;script src="https://cdn.plugo.dev/widget.js" async&gt;&lt;/script&gt;</pre>
      <h2>Configuration</h2>
      <p>You can customize the widget with these options:</p>
      <p><code>primaryColor</code> — Set the theme color (hex format, e.g. <code>#6366f1</code>)</p>
      <p><code>greeting</code> — Welcome message shown when the chat opens</p>
      <p><code>position</code> — Widget position: <code>bottom-right</code> or <code>bottom-left</code></p>
      <p><code>darkMode</code> — Enable dark theme (<code>true</code> / <code>false</code>)</p>
      <h2>Need Help?</h2>
      <p>Try asking the chat widget! It can answer questions about this documentation.</p>
    </div>
  </div>
</div>
${getWidgetScript(site, dark)}
</body></html>`;
}

function getDemoBlankPage(site: any, dark: boolean): string {
  if (!site) return "";
  const safeName = escapeHtml(site.name || "");
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${safeName}</title>
<style>
  ${baseStyles(dark)}
  body { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .center { text-align: center; }
  .center p { font-size: 0.875rem; }
</style></head><body>
<div class="center">
  <p class="muted">Blank page — only the chat widget is loaded.</p>
</div>
${getWidgetScript(site, dark)}
</body></html>`;
}
