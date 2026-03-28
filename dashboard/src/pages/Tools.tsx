import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getTools, createTool, deleteTool, testTool } from "../lib/api";
import { Wrench, Plus, Trash2, Play, CheckCircle } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { FormField } from "../components/FormField";
import { EmptyState } from "../components/EmptyState";

export default function Tools() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, any>>({});

  // Form state
  const [form, setForm] = useState({
    name: "",
    description: "",
    method: "GET",
    url: "",
    auth_type: "none",
    auth_value: "",
    params_schema: "{}",
  });

  const { data: tools = [], isLoading } = useQuery({
    queryKey: ["tools", siteId],
    queryFn: () => getTools(siteId!),
    enabled: !!siteId,
  });

  const createMutation = useMutation({
    mutationFn: createTool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
      setShowAdd(false);
      setForm({ name: "", description: "", method: "GET", url: "", auth_type: "none", auth_value: "", params_schema: "{}" });
      toast.success("Tool created");
    },
    onError: () => toast.error("Failed to create tool"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
      toast.success("Tool deleted");
    },
    onError: () => toast.error("Failed to delete tool"),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteId) return;
    let params = {};
    try { params = JSON.parse(form.params_schema); } catch {}
    createMutation.mutate({
      site_id: siteId,
      name: form.name,
      description: form.description,
      method: form.method,
      url: form.url,
      auth_type: form.auth_type === "none" ? null : form.auth_type,
      auth_value: form.auth_value || null,
      params_schema: params,
    });
  };

  const handleTest = async (toolId: string) => {
    try {
      const result = await testTool(toolId, {});
      setTestResults((prev) => ({ ...prev, [toolId]: result }));
      toast.success("Test completed");
    } catch {
      toast.error("Test failed");
    }
  };

  return (
    <div className="max-w-4xl">
      <PageHeader title="API Tools" subtitle="Let the bot call your website's APIs">
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> Add Tool
        </button>
      </PageHeader>

      {showAdd && (
        <form onSubmit={handleCreate} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold mb-4">Add API Tool</h3>
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Tool Name">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="search_products" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label="Method">
              <select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none">
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
            </FormField>
            <FormField label="Description (helps the bot decide when to call this tool)" className="col-span-2">
              <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Search products by name or category" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label="URL" className="col-span-2">
              <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://api.example.com/products" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label="Auth Type">
              <select value={form.auth_type} onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none">
                <option value="none">None</option><option value="bearer">Bearer Token</option>
                <option value="api_key">API Key</option><option value="basic">Basic Auth</option>
              </select>
            </FormField>
            <FormField label="Auth Value">
              <input value={form.auth_value} onChange={(e) => setForm({ ...form, auth_value: e.target.value })}
                placeholder="Token or key..." type="password" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </FormField>
            <FormField label="Params Schema (JSON)" className="col-span-2">
              <textarea value={form.params_schema} onChange={(e) => setForm({ ...form, params_schema: e.target.value })}
                rows={4} placeholder='{"q": {"type": "string", "description": "Search query", "required": true}}'
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm" />
            </FormField>
          </div>
          <div className="flex gap-3 mt-4">
            <button type="submit" disabled={createMutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg">
              {createMutation.isPending ? "Saving..." : "Save Tool"}
            </button>
            <button type="button" onClick={() => setShowAdd(false)} className="text-gray-500 px-4 py-2">Cancel</button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-gray-400">Loading...</div>
      ) : tools.length === 0 ? (
        <EmptyState icon={Wrench} message="No tools yet. Add an API tool to enable the bot to perform actions." />
      ) : (
        <div className="space-y-3">
          {tools.map((tool: any) => (
            <div key={tool.id} className="bg-white p-4 rounded-xl border border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">{tool.method}</span>
                    <h4 className="font-medium">{tool.name}</h4>
                    {tool.enabled && <CheckCircle className="w-3.5 h-3.5 text-green-500" />}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{tool.description}</p>
                  <p className="text-xs text-gray-400 mt-1 font-mono">{tool.url}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => handleTest(tool.id)} className="text-blue-500 hover:text-blue-700 p-1">
                    <Play className="w-4 h-4" />
                  </button>
                  <button onClick={() => deleteMutation.mutate(tool.id)} className="text-gray-400 hover:text-red-500 p-1">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {testResults[tool.id] && (
                <pre className="mt-3 p-3 bg-gray-50 rounded-lg text-xs font-mono overflow-auto max-h-40">
                  {JSON.stringify(testResults[tool.id], null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
