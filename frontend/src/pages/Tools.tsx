import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getTools,
  createTool,
  updateTool,
  deleteTool,
  testTool,
  type Tool,
  type UpdateToolData,
} from "../lib/api";
import { Wrench, Plus, Trash2, Play, CheckCircle, Pencil, X, ToggleLeft, ToggleRight } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { FormField } from "../components/FormField";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useLocale } from "../lib/useLocale";

type ParamRow = { name: string; type: string; description: string; required: boolean };
type ParamSchemaField = { type?: string; description?: string; required?: boolean };

const emptyForm = {
  name: "",
  description: "",
  method: "GET",
  url: "",
  auth_type: "none",
  auth_value: "",
  params_schema: "{}",
};

export default function Tools() {
  const { siteId } = useParams<{ siteId: string }>();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, unknown>>({});
  const [form, setForm] = useState({ ...emptyForm });
  const [useBuilder, setUseBuilder] = useState(false);
  const [params, setParams] = useState<ParamRow[]>([]);
  const [testParamsJson, setTestParamsJson] = useState<Record<string, string>>({});
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

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
      setForm({ ...emptyForm });
      toast.success("Tool created");
    },
    onError: () => toast.error("Failed to create tool"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateToolData }) => updateTool(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
      setEditingId(null);
      setForm({ ...emptyForm });
      toast.success(t("tools.updateSuccess"));
    },
    onError: () => toast.error(t("tools.updateFailed")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
      toast.success("Tool deleted");
    },
    onError: () => toast.error("Failed to delete tool"),
  });

  const startEdit = (tool: Tool) => {
    setEditingId(tool.id);
    setShowAdd(false);
    setForm({
      name: tool.name || "",
      description: tool.description || "",
      method: tool.method || "GET",
      url: tool.url || "",
      auth_type: tool.auth_type || "none",
      auth_value: tool.auth_value || "",
      params_schema: tool.params_schema ? JSON.stringify(tool.params_schema, null, 2) : "{}",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm({ ...emptyForm });
  };

  // Sync visual builder → JSON
  const syncBuilderToJson = () => {
    const schema: Record<string, ParamSchemaField> = {};
    params.forEach((p) => {
      schema[p.name] = { type: p.type, description: p.description, required: p.required };
    });
    setForm({ ...form, params_schema: JSON.stringify(schema, null, 2) });
  };

  // Sync JSON → visual builder
  const syncJsonToBuilder = () => {
    try {
      const parsed = JSON.parse(form.params_schema) as Record<string, ParamSchemaField>;
      const entries = Object.entries(parsed).map(([name, val]) => ({
        name,
        type: val.type || "string",
        description: val.description || "",
        required: val.required || false,
      }));
      setParams(entries);
    } catch {
      void 0;
    }
  };

  const addParam = () => {
    setParams([...params, { name: "", type: "string", description: "", required: false }]);
  };

  const updateParam = (index: number, field: keyof ParamRow, value: string | boolean) => {
    const next = [...params];
    next[index] = { ...next[index], [field]: value };
    setParams(next);
    // Auto-sync to JSON
    const schema: Record<string, ParamSchemaField> = {};
    next.forEach((p) => {
      if (p.name) schema[p.name] = { type: p.type, description: p.description, required: p.required };
    });
    setForm({ ...form, params_schema: JSON.stringify(schema, null, 2) });
  };

  const removeParam = (index: number) => {
    const next = params.filter((_, i) => i !== index);
    setParams(next);
    const schema: Record<string, ParamSchemaField> = {};
    next.forEach((p) => {
      if (p.name) schema[p.name] = { type: p.type, description: p.description, required: p.required };
    });
    setForm({ ...form, params_schema: JSON.stringify(schema, null, 2) });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteId) return;
    let parsedParams = {};
    try {
      parsedParams = JSON.parse(form.params_schema);
    } catch {
      toast.error("Invalid JSON in parameters schema");
      return;
    }

    const payload = {
      name: form.name,
      description: form.description,
      method: form.method,
      url: form.url,
      auth_type: form.auth_type === "none" ? undefined : form.auth_type,
      auth_value: form.auth_value || undefined,
      params_schema: parsedParams,
    };

    if (editingId) {
      updateMutation.mutate({
        id: editingId,
        data: {
          ...payload,
          auth_type: form.auth_type === "none" ? null : form.auth_type,
          auth_value: form.auth_value || null,
        },
      });
    } else {
      createMutation.mutate({ site_id: siteId, ...payload });
    }
  };

  const handleTest = async (toolId: string) => {
    let parsedTestParams = {};
    const rawJson = testParamsJson[toolId];
    if (rawJson && rawJson.trim()) {
      try {
        parsedTestParams = JSON.parse(rawJson);
      } catch {
        toast.error("Invalid JSON in test parameters");
        return;
      }
    }
    try {
      const result = await testTool(toolId, parsedTestParams);
      setTestResults((prev) => ({ ...prev, [toolId]: result }));
      toast.success("Test completed");
    } catch {
      toast.error("Test failed");
    }
  };

  const isFormOpen = showAdd || editingId;
  const isPending = createMutation.isPending || updateMutation.isPending;

  const renderForm = () => (
    <form onSubmit={handleSubmit} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">{editingId ? t("tools.editTool") : t("tools.addTool")}</h3>
        <button type="button" onClick={() => { setShowAdd(false); cancelEdit(); }} className="text-gray-400 hover:text-gray-600">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <FormField label={t("tools.toolName")}>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="search_products" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
        </FormField>
        <FormField label={t("tools.method")}>
          <select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 outline-none">
            <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
          </select>
        </FormField>
        <FormField label={t("tools.description")} className="lg:col-span-2">
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Search products by name or category" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
        </FormField>
        <FormField label={t("tools.url")} className="lg:col-span-2">
          <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
            placeholder="https://api.example.com/products" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
        </FormField>
        <FormField label={t("tools.authType")}>
          <select value={form.auth_type} onChange={(e) => setForm({ ...form, auth_type: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 outline-none">
            <option value="none">None</option><option value="bearer">Bearer Token</option>
            <option value="api_key">API Key</option><option value="basic">Basic Auth</option>
          </select>
        </FormField>
        <FormField label={t("tools.authValue")}>
          <input value={form.auth_value} onChange={(e) => setForm({ ...form, auth_value: e.target.value })}
            placeholder="Token or key..." type="password" className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
        </FormField>
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm font-medium text-gray-700">
              {useBuilder ? t("tools.paramBuilder") : t("tools.paramsSchema")}
            </label>
            <button
              type="button"
              onClick={() => {
                if (useBuilder) {
                  syncBuilderToJson();
                } else {
                  syncJsonToBuilder();
                }
                setUseBuilder(!useBuilder);
              }}
              className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1"
            >
              {useBuilder ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
              {useBuilder ? t("tools.switchToJson") : t("tools.switchToBuilder")}
            </button>
          </div>

          {useBuilder ? (
            <div className="border rounded-lg p-3 space-y-2">
              {params.map((p, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input
                    value={p.name}
                    onChange={(e) => updateParam(i, "name", e.target.value)}
                    placeholder={t("tools.paramName")}
                    className="flex-1 border rounded px-2 py-1.5 text-sm outline-none"
                  />
                  <select
                    value={p.type}
                    onChange={(e) => updateParam(i, "type", e.target.value)}
                    className="w-24 border rounded px-2 py-1.5 text-sm outline-none"
                  >
                    <option value="string">string</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                    <option value="array">array</option>
                    <option value="object">object</option>
                  </select>
                  <input
                    value={p.description}
                    onChange={(e) => updateParam(i, "description", e.target.value)}
                    placeholder={t("tools.paramDesc")}
                    className="flex-1 border rounded px-2 py-1.5 text-sm outline-none"
                  />
                  <label className="flex items-center gap-1 text-xs text-gray-500 shrink-0">
                    <input
                      type="checkbox"
                      checked={p.required}
                      onChange={(e) => updateParam(i, "required", e.target.checked)}
                      className="rounded"
                    />
                    {t("tools.paramRequired")}
                  </label>
                  <button type="button" onClick={() => removeParam(i)} className="text-gray-400 hover:text-red-500">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addParam}
                className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1"
              >
                <Plus className="w-3 h-3" /> {t("tools.addParam")}
              </button>
            </div>
          ) : (
            <textarea value={form.params_schema} onChange={(e) => setForm({ ...form, params_schema: e.target.value })}
              rows={4} placeholder='{"q": {"type": "string", "description": "Search query", "required": true}}'
              className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 font-mono text-sm" />
          )}
        </div>
      </div>
      <div className="flex gap-3 mt-4">
        <button type="submit" disabled={isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg">
          {isPending ? t("settings.saving") : editingId ? t("tools.saveTool") : t("tools.saveTool")}
        </button>
        <button type="button" onClick={() => { setShowAdd(false); cancelEdit(); }} className="text-gray-500 px-4 py-2">
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );

  return (
    <div>
      <PageHeader title={t("tools.title")} subtitle={t("tools.subtitle")}>
        <button
          onClick={() => { setShowAdd(true); cancelEdit(); }}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-4 h-4" /> {t("tools.addTool")}
        </button>
      </PageHeader>

      {isFormOpen && renderForm()}

      {/* Single-item delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={t("common.delete")}
        message={t("tools.deleteConfirm") === "tools.deleteConfirm" ? "Are you sure you want to delete this tool? This action cannot be undone." : t("tools.deleteConfirm")}
        confirmLabel={t("common.delete")}
        danger
        loading={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget, {
              onSettled: () => setDeleteTarget(null),
            });
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : tools.length === 0 ? (
        <EmptyState icon={Wrench} message={t("tools.noTools")} />
      ) : (
        <div className="space-y-3">
          {tools.map((tool) => (
            <div key={tool.id} className={`bg-white p-4 rounded-xl border ${editingId === tool.id ? "border-primary-300 bg-primary-50" : "border-gray-200"}`}>
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
                  <button onClick={() => handleTest(tool.id)} className="text-blue-500 hover:text-blue-700 p-1" title="Test">
                    <Play className="w-4 h-4" />
                  </button>
                  <button onClick={() => startEdit(tool)} className="text-gray-400 hover:text-primary-600 p-1" title={t("common.edit")}>
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button onClick={() => setDeleteTarget(tool.id)} className="text-gray-400 hover:text-red-500 p-1" title={t("common.delete")}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="mt-3">
                <textarea
                  value={testParamsJson[tool.id] || ""}
                  onChange={(e) => setTestParamsJson((prev) => ({ ...prev, [tool.id]: e.target.value }))}
                  placeholder='Test parameters JSON, e.g. {"q": "shoes"}'
                  rows={2}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              {tool.id in testResults ? (
                <pre className="mt-3 p-3 bg-gray-50 rounded-lg text-xs font-mono overflow-auto max-h-40">
                  {JSON.stringify(testResults[tool.id], null, 2)}
                </pre>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
