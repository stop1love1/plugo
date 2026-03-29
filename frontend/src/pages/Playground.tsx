import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite, type Site } from "../lib/api";
import { useLocale } from "../lib/useLocale";
import { Monitor, Smartphone, Tablet, RotateCcw, ExternalLink, Globe, Play } from "lucide-react";

type Device = "desktop" | "tablet" | "mobile";

const deviceStyles: Record<Device, { width: string; label: string }> = {
  desktop: { width: "100%", label: "Desktop" },
  tablet: { width: "768px", label: "Tablet" },
  mobile: { width: "375px", label: "Mobile" },
};

function buildPlaygroundHtml(site: Site, siteUrl: string): string {
  const backendUrl = import.meta.env.VITE_BACKEND_URL || __BACKEND_URL__;
  const wsUrl = backendUrl.replace(/^http/, "ws");

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${site.name || "Playground"}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body, html { width: 100%; height: 100%; overflow: hidden; }
  iframe { width: 100%; height: 100%; border: 0; }
</style>
</head><body>
<iframe src="${siteUrl}" sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>
<script>
  window.PlugoConfig = {
    token: ${JSON.stringify(site.token || "")},
    serverUrl: ${JSON.stringify(wsUrl)},
    primaryColor: ${JSON.stringify(site.primary_color || "#6366f1")},
    greeting: ${JSON.stringify(site.greeting || "Hello! How can I help you?")},
    position: ${JSON.stringify(site.position || "bottom-right")},
    widgetTitle: ${JSON.stringify(site.widget_title || "")},
    botAvatar: ${JSON.stringify(site.bot_avatar || "")},
    headerSubtitle: ${JSON.stringify(site.header_subtitle || "")},
    inputPlaceholder: ${JSON.stringify(site.input_placeholder || "")},
    bubbleSize: ${JSON.stringify(site.bubble_size || "medium")},
    darkMode: ${site.dark_mode === "dark" ? "true" : site.dark_mode === "light" ? "false" : "undefined"},
  };
</script>
<script src="${backendUrl}/static/widget.js" async></script>
</body></html>`;
}

export default function Playground() {
  const { siteId } = useParams<{ siteId: string }>();
  const { t } = useLocale();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [key, setKey] = useState(0);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const siteUrl = site?.url
    ? (site.url.startsWith("http") ? site.url : `https://${site.url}`)
    : "";

  // Write HTML into iframe whenever site/key changes
  useEffect(() => {
    if (!iframeRef.current || !site || !siteUrl) return;
    const doc = iframeRef.current.contentDocument;
    if (doc) {
      doc.open();
      doc.write(buildPlaygroundHtml(site, siteUrl));
      doc.close();
    }
  }, [site, siteUrl, key]);

  const handleReload = () => setKey((k) => k + 1);

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
      <div className="bg-white border border-gray-200 rounded-t-xl px-4 py-2 flex items-center gap-3">
        <Globe className="w-4 h-4 text-gray-400 shrink-0" />
        <span className="flex-1 text-sm text-gray-600 truncate" title={siteUrl}>
          {siteUrl || t("playground.noUrl")}
        </span>

        <div className="w-px h-5 bg-gray-200" />

        {([
          { id: "desktop" as Device, icon: Monitor },
          { id: "tablet" as Device, icon: Tablet },
          { id: "mobile" as Device, icon: Smartphone },
        ]).map(({ id, icon: Icon }) => (
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

        <div className="w-px h-5 bg-gray-200" />

        <button
          onClick={handleReload}
          disabled={!siteUrl}
          className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-30"
          title={t("playground.reload")}
        >
          <RotateCcw className="w-4 h-4" />
        </button>

        <button
          onClick={() => siteUrl && window.open(siteUrl, "_blank")}
          disabled={!siteUrl}
          className="p-1.5 rounded text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-30"
          title={t("playground.openExternal")}
        >
          <ExternalLink className="w-4 h-4" />
        </button>
      </div>

      {/* Preview area */}
      <div className="flex-1 bg-gray-100 border border-t-0 border-gray-200 rounded-b-xl flex items-start justify-center overflow-hidden p-4">
        {siteUrl ? (
          <div
            className="bg-white shadow-lg rounded-lg overflow-hidden transition-all duration-300 h-full"
            style={{ width: deviceStyle.width, maxWidth: "100%" }}
          >
            <iframe
              ref={iframeRef}
              key={key}
              title="Playground"
              className="w-full h-full border-0"
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
            <Globe className="w-16 h-16 text-gray-300" />
            <p className="text-sm">{t("playground.noUrl")}</p>
          </div>
        )}
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
