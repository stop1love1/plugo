import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite } from "../lib/api";
import { Copy, Check, Code, Eye, Sliders, ShieldCheck, AlertTriangle } from "lucide-react";
import { useLocale } from "../lib/useLocale";

export default function Embed() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const [copied, setCopied] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const previewRef = useRef<HTMLIFrameElement>(null);

  // Interactive configurator state
  const [previewColor, setPreviewColor] = useState("#6366f1");
  const [previewPosition, setPreviewPosition] = useState("bottom-right");
  const [previewGreeting, setPreviewGreeting] = useState("");
  const [previewDarkMode, setPreviewDarkMode] = useState(false);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  // Sync config from site data
  useEffect(() => {
    if (site) {
      setPreviewColor(site.primary_color || "#6366f1");
      setPreviewPosition(site.position || "bottom-right");
      setPreviewGreeting(site.greeting || "");
    }
  }, [site]);

  const backendUrl = import.meta.env.VITE_BACKEND_URL || __BACKEND_URL__;

  const buildConfigStr = (s: typeof site, includeServerUrl: boolean) => {
    if (!s) return "";
    const lines = [`    token: "${s.token}"`];
    if (includeServerUrl) lines.push(`    serverUrl: "${backendUrl.replace(/^http/, "ws")}"`);
    lines.push(`    primaryColor: "${s.primary_color}"`);
    if (s.greeting) lines.push(`    greeting: "${s.greeting}"`);
    lines.push(`    position: "${s.position || "bottom-right"}"`);
    if (s.dark_mode && s.dark_mode !== "auto") lines.push(`    darkMode: ${s.dark_mode === "dark"}`);
    if (s.widget_title) lines.push(`    widgetTitle: "${s.widget_title}"`);
    if (s.bot_avatar) lines.push(`    botAvatar: "${s.bot_avatar}"`);
    if (s.header_subtitle) lines.push(`    headerSubtitle: "${s.header_subtitle}"`);
    if (s.input_placeholder) lines.push(`    inputPlaceholder: "${s.input_placeholder}"`);
    if (s.auto_open_delay) lines.push(`    autoOpenDelay: ${s.auto_open_delay}`);
    if (s.bubble_size && s.bubble_size !== "medium") lines.push(`    bubbleSize: "${s.bubble_size}"`);
    return lines.join(",\n");
  };

  const embedCode = site
    ? `<!-- Plugo Chat Widget -->
<script>
  window.PlugoConfig = {
${buildConfigStr(site, true)}
  };
</script>
<script src="${backendUrl}/static/widget.js" async></script>`
    : "";

  const productionCode = site
    ? `<!-- Plugo Chat Widget -->
<script>
  window.PlugoConfig = {
${buildConfigStr(site, false)}
  };
</script>
<script src="https://cdn.plugo.dev/widget.js" async></script>`
    : "";

  const previewHtml = site
    ? `<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{margin:0;font-family:system-ui,sans-serif;background:#f9fafb;display:flex;align-items:center;justify-content:center;height:100vh;color:#6b7280;}
p{text-align:center;font-size:14px;}</style></head>
<body><p>Widget preview — click the chat bubble to test</p>
<script>window.PlugoConfig={token:${JSON.stringify(site.token)},serverUrl:${JSON.stringify(backendUrl.replace(/^http/, "ws"))},primaryColor:${JSON.stringify(previewColor)},greeting:${JSON.stringify(previewGreeting)},position:${JSON.stringify(previewPosition)},darkMode:${JSON.stringify(previewDarkMode)}};</script>
<script src="${backendUrl}/static/widget.js" async></script>
</body></html>`
    : "";

  // Reload preview when config changes
  useEffect(() => {
    if (showPreview && previewRef.current && previewHtml) {
      const doc = previewRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(previewHtml);
        doc.close();
      }
    }
  }, [showPreview, previewHtml, previewColor, previewPosition, previewGreeting, previewDarkMode]);

  const handleCopy = (code: string, id: string) => {
    navigator.clipboard.writeText(code);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("embed.title")}</h1>
      <p className="text-gray-500 mb-8">{t("embed.subtitle")}</p>

      {/* Interactive Configurator + Preview */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-gray-500" />
            <span className="font-medium text-sm">{t("embed.configurator")}</span>
          </div>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
          >
            <Eye className="w-4 h-4" />
            {showPreview ? t("embed.hidePreview") : t("embed.showPreview")}
          </button>
        </div>

        {/* Configurator controls */}
        <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">{t("embed.primaryColor")}</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={previewColor}
                onChange={(e) => setPreviewColor(e.target.value)}
                className="w-8 h-8 rounded border cursor-pointer"
              />
              <input
                value={previewColor}
                onChange={(e) => setPreviewColor(e.target.value)}
                className="w-24 border rounded px-2 py-1 text-xs font-mono outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">{t("embed.position")}</label>
            <select
              value={previewPosition}
              onChange={(e) => setPreviewPosition(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm outline-none"
            >
              <option value="bottom-right">{t("embed.positionBottomRight")}</option>
              <option value="bottom-left">{t("embed.positionBottomLeft")}</option>
            </select>
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">{t("embed.greeting")}</label>
            <input
              value={previewGreeting}
              onChange={(e) => setPreviewGreeting(e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm outline-none"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={previewDarkMode}
              onChange={(e) => setPreviewDarkMode(e.target.checked)}
              className="rounded"
            />
            <label className="text-xs font-medium text-gray-600">{t("embed.darkMode")}</label>
          </div>
        </div>

        {showPreview && (
          <div className="border-t border-gray-100">
            <p className="text-xs text-gray-400 px-4 pt-3">{t("embed.previewDesc")}</p>
            <iframe
              ref={previewRef}
              title="Widget Preview"
              className="w-full border-0 rounded-b-xl"
              style={{ height: "500px" }}
              sandbox="allow-scripts allow-same-origin"
            />
          </div>
        )}
      </div>

      {/* Development */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-gray-500" />
            <span className="font-medium text-sm">{t("embed.development")}</span>
          </div>
          <button
            onClick={() => handleCopy(embedCode, "dev")}
            className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
          >
            {copied === "dev" ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied === "dev" ? t("embed.copied") : t("embed.copy")}
          </button>
        </div>
        <pre className="p-4 text-sm font-mono text-gray-700 overflow-x-auto bg-gray-50 rounded-b-xl">
          {embedCode}
        </pre>
      </div>

      {/* Production */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-gray-500" />
            <span className="font-medium text-sm">{t("embed.production")}</span>
          </div>
          <button
            onClick={() => handleCopy(productionCode, "prod")}
            className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
          >
            {copied === "prod" ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied === "prod" ? t("embed.copied") : t("embed.copy")}
          </button>
        </div>
        <pre className="p-4 text-sm font-mono text-gray-700 overflow-x-auto bg-gray-50 rounded-b-xl">
          {productionCode}
        </pre>
      </div>

      {/* Approval status */}
      {site && (
        <div className={`rounded-xl border p-4 mb-6 flex items-start gap-3 ${
          site.is_approved
            ? "bg-green-50 border-green-200"
            : "bg-amber-50 border-amber-200"
        }`}>
          {site.is_approved ? (
            <>
              <ShieldCheck className="w-5 h-5 text-green-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium text-green-800 text-sm">{t("embed.siteApproved")}</p>
                <p className="text-green-700 text-xs mt-1">{t("embed.siteApprovedDesc")}</p>
              </div>
            </>
          ) : (
            <>
              <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium text-amber-800 text-sm">{t("embed.sitePending")}</p>
                <p className="text-amber-700 text-xs mt-1">{t("embed.sitePendingDesc")}</p>
              </div>
            </>
          )}
        </div>
      )}

      {/* Auth guide */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="p-4 border-b border-gray-100">
          <h3 className="font-semibold text-sm">{t("embed.authGuide")}</h3>
        </div>
        <div className="p-4 text-sm text-gray-700 space-y-3">
          <div className="flex gap-3">
            <span className="bg-primary-100 text-primary-700 font-bold text-xs w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5">1</span>
            <p>{t("embed.authStep1")}</p>
          </div>
          <div className="flex gap-3">
            <span className="bg-primary-100 text-primary-700 font-bold text-xs w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5">2</span>
            <p>{t("embed.authStep2")}</p>
          </div>
          <div className="flex gap-3">
            <span className="bg-primary-100 text-primary-700 font-bold text-xs w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5">3</span>
            <p>{t("embed.authStep3")}</p>
          </div>
          <div className="flex gap-3">
            <span className="bg-primary-100 text-primary-700 font-bold text-xs w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5">4</span>
            <p>{t("embed.authStep4")}</p>
          </div>
        </div>
      </div>

      {/* Config options */}
      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="font-semibold mb-4">{t("embed.configOptions")}</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="pb-2">{t("embed.tableOption")}</th>
              <th className="pb-2">{t("embed.tableType")}</th>
              <th className="pb-2">{t("embed.tableDescription")}</th>
            </tr>
          </thead>
          <tbody className="text-gray-700">
            {[
              ["token", "string", t("embed.optToken")],
              ["serverUrl", "string", t("embed.optServerUrl")],
              ["primaryColor", "string", t("embed.optColor")],
              ["greeting", "string", t("embed.optGreeting")],
              ["position", "string", t("embed.optPosition")],
              ["darkMode", "boolean", t("embed.optDarkMode")],
              ["language", "string", t("embed.optLanguage")],
            ].map(([opt, type, desc], i) => (
              <tr key={i} className="border-b border-gray-50 last:border-0">
                <td className="py-2 font-mono text-xs">{opt}</td>
                <td className="py-2">{type}</td>
                <td className="py-2">{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
