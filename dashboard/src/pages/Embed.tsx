import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite } from "../lib/api";
import { Copy, Check, Code } from "lucide-react";

export default function Embed() {
  const { siteId } = useParams<{ siteId: string }>();
  const [copied, setCopied] = useState(false);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const embedCode = site
    ? `<!-- Plugo Chat Widget -->
<script>
  window.PlugoConfig = {
    token: "${site.token}",
    serverUrl: "ws://localhost:8000",
    primaryColor: "${site.primary_color}",
    greeting: "${site.greeting}"
  };
</script>
<script src="http://localhost:8000/static/widget.js" async></script>`
    : "";

  const productionCode = site
    ? `<!-- Plugo Chat Widget -->
<script>
  window.PlugoConfig = {
    token: "${site.token}",
    primaryColor: "${site.primary_color}",
    greeting: "${site.greeting}"
  };
</script>
<script src="https://cdn.plugo.dev/widget.js" async></script>`
    : "";

  const handleCopy = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Embed Code</h1>
      <p className="text-gray-500 mb-8">
        Copy đoạn code bên dưới và dán vào website của bạn, trước thẻ &lt;/body&gt;
      </p>

      {/* Development */}
      <div className="bg-white rounded-xl border border-gray-200 mb-6">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-gray-500" />
            <span className="font-medium text-sm">Development (localhost)</span>
          </div>
          <button
            onClick={() => handleCopy(embedCode)}
            className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? "Copied!" : "Copy"}
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
            <span className="font-medium text-sm">Production</span>
          </div>
          <button
            onClick={() => handleCopy(productionCode)}
            className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
          >
            <Copy className="w-4 h-4" /> Copy
          </button>
        </div>
        <pre className="p-4 text-sm font-mono text-gray-700 overflow-x-auto bg-gray-50 rounded-b-xl">
          {productionCode}
        </pre>
      </div>

      {/* Config options */}
      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="font-semibold mb-4">Tuỳ chọn cấu hình</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="pb-2">Option</th>
              <th className="pb-2">Type</th>
              <th className="pb-2">Mô tả</th>
            </tr>
          </thead>
          <tbody className="text-gray-700">
            <tr className="border-b border-gray-50">
              <td className="py-2 font-mono text-xs">token</td>
              <td className="py-2">string</td>
              <td className="py-2">Token xác thực site (bắt buộc)</td>
            </tr>
            <tr className="border-b border-gray-50">
              <td className="py-2 font-mono text-xs">serverUrl</td>
              <td className="py-2">string</td>
              <td className="py-2">URL backend server</td>
            </tr>
            <tr className="border-b border-gray-50">
              <td className="py-2 font-mono text-xs">primaryColor</td>
              <td className="py-2">string</td>
              <td className="py-2">Màu chủ đạo (hex)</td>
            </tr>
            <tr className="border-b border-gray-50">
              <td className="py-2 font-mono text-xs">greeting</td>
              <td className="py-2">string</td>
              <td className="py-2">Lời chào khi mở chat</td>
            </tr>
            <tr>
              <td className="py-2 font-mono text-xs">position</td>
              <td className="py-2">string</td>
              <td className="py-2">"bottom-right" hoặc "bottom-left"</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
