import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSite, updateSite, getProviders } from "../lib/api";
import { Save, Check } from "lucide-react";

export default function Settings() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: providers = [] } = useQuery({
    queryKey: ["providers"],
    queryFn: getProviders,
  });

  const [form, setForm] = useState({
    name: "",
    llm_provider: "",
    llm_model: "",
    primary_color: "#6366f1",
    greeting: "",
    position: "bottom-right",
    allowed_domains: "",
  });

  useEffect(() => {
    if (site) {
      setForm({
        name: site.name,
        llm_provider: site.llm_provider,
        llm_model: site.llm_model,
        primary_color: site.primary_color,
        greeting: site.greeting,
        position: site.position,
        allowed_domains: site.allowed_domains,
      });
    }
  }, [site]);

  const mutation = useMutation({
    mutationFn: (data: any) => updateSite(siteId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(form);
  };

  const currentProvider = providers.find((p: any) => p.id === form.llm_provider);

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Settings</h1>
      <p className="text-gray-500 mb-8">Configure your site and widget</p>

      <form onSubmit={handleSave} className="space-y-6">
        {/* General */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">General</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Website Name</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Domain Whitelist (comma-separated)</label>
              <input value={form.allowed_domains} onChange={(e) => setForm({ ...form, allowed_domains: e.target.value })}
                placeholder="example.com, app.example.com"
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
        </div>

        {/* LLM */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">LLM Provider</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
              <select value={form.llm_provider} onChange={(e) => {
                const p = providers.find((p: any) => p.id === e.target.value);
                setForm({
                  ...form,
                  llm_provider: e.target.value,
                  llm_model: p?.models?.[0]?.id || "",
                });
              }} className="w-full border rounded-lg px-3 py-2 outline-none">
                {providers.map((p: any) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
              <select value={form.llm_model} onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none">
                {currentProvider?.models?.map((m: any) => (
                  <option key={m.id} value={m.id}>{m.name} — {m.description}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Widget */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">Widget</h3>
          <div className="space-y-4">
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">Primary Color</label>
                <div className="flex items-center gap-2">
                  <input type="color" value={form.primary_color}
                    onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
                    className="w-10 h-10 rounded border cursor-pointer" />
                  <input value={form.primary_color}
                    onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
                    className="w-28 border rounded-lg px-3 py-2 font-mono text-sm outline-none" />
                </div>
              </div>
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">Position</label>
                <select value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 outline-none">
                  <option value="bottom-right">Bottom Right</option>
                  <option value="bottom-left">Bottom Left</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Greeting Message</label>
              <input value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
        </div>

        <button type="submit" disabled={mutation.isPending}
          className="flex items-center gap-2 bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50">
          {saved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {saved ? "Saved!" : mutation.isPending ? "Saving..." : "Save Changes"}
        </button>
      </form>
    </div>
  );
}
