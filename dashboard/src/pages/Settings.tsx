import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getSite, updateSite, deleteSite, getProviders, getLLMKeys, saveLLMKey, deleteLLMKey } from "../lib/api";
import { Save, Trash2, AlertTriangle, Key, Eye, EyeOff, Check, X } from "lucide-react";
import { useLocale } from "../lib/useLocale";

export default function Settings() {
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useLocale();
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
    suggestions: "",
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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
        suggestions: (site.suggestions || []).join(", "),
      });
    }
  }, [site]);

  // Track unsaved changes
  const hasChanges = useMemo(() => {
    if (!site) return false;
    return (
      form.name !== site.name ||
      form.llm_provider !== site.llm_provider ||
      form.llm_model !== site.llm_model ||
      form.primary_color !== site.primary_color ||
      form.greeting !== site.greeting ||
      form.position !== site.position ||
      form.allowed_domains !== site.allowed_domains ||
      form.suggestions !== (site.suggestions || []).join(", ")
    );
  }, [form, site]);

  // Inline validation
  const validate = (field: string, value: string) => {
    const newErrors = { ...errors };
    if (field === "primary_color") {
      if (!/^#[0-9A-Fa-f]{6}$/.test(value)) {
        newErrors.primary_color = t("settings.invalidColor");
      } else {
        delete newErrors.primary_color;
      }
    }
    if (field === "allowed_domains") {
      const domains = value.split(",").map((d) => d.trim()).filter(Boolean);
      const invalidDomain = domains.find((d) => d.includes(" ") || (!d.includes(".") && d.length > 0));
      if (invalidDomain) {
        newErrors.allowed_domains = t("settings.invalidUrl");
      } else {
        delete newErrors.allowed_domains;
      }
    }
    setErrors(newErrors);
  };

  const mutation = useMutation({
    mutationFn: (data: any) => updateSite(siteId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      toast.success("Settings saved");
    },
    onError: () => toast.error("Failed to save settings"),
  });

  const deletesMutation = useMutation({
    mutationFn: () => deleteSite(siteId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      toast.success("Site deleted");
      navigate("/");
    },
    onError: () => toast.error("Failed to delete site"),
  });

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (Object.keys(errors).length > 0) return;
    const { suggestions: suggestionsStr, ...rest } = form;
    const suggestions = suggestionsStr
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    mutation.mutate({ ...rest, suggestions });
  };

  const currentProvider = providers.find((p: any) => p.id === form.llm_provider);

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{t("settings.title")}</h1>
      <p className="text-gray-500 mb-8">{t("settings.widget")}</p>

      {hasChanges && (
        <div className="mb-4 px-4 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          {t("settings.unsavedChanges")}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* General */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("settings.general")}</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.websiteName")}</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.domainWhitelist")}</label>
              <input value={form.allowed_domains}
                onChange={(e) => {
                  setForm({ ...form, allowed_domains: e.target.value });
                  validate("allowed_domains", e.target.value);
                }}
                placeholder="example.com, app.example.com"
                className={`w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 ${errors.allowed_domains ? "border-red-300" : ""}`} />
              {errors.allowed_domains && (
                <p className="text-xs text-red-500 mt-1">{errors.allowed_domains}</p>
              )}
            </div>
          </div>
        </div>

        {/* API Keys */}
        <LLMKeysSection providers={providers} />

        {/* LLM */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("settings.llm")}</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.provider")}</label>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.model")}</label>
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
          <h3 className="font-semibold mb-4">{t("settings.widget")}</h3>
          <div className="space-y-4">
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.primaryColor")}</label>
                <div className="flex items-center gap-2">
                  <input type="color" value={form.primary_color}
                    onChange={(e) => {
                      setForm({ ...form, primary_color: e.target.value });
                      validate("primary_color", e.target.value);
                    }}
                    className="w-10 h-10 rounded border cursor-pointer" />
                  <input value={form.primary_color}
                    onChange={(e) => {
                      setForm({ ...form, primary_color: e.target.value });
                      validate("primary_color", e.target.value);
                    }}
                    className={`w-28 border rounded-lg px-3 py-2 font-mono text-sm outline-none ${errors.primary_color ? "border-red-300" : ""}`} />
                </div>
                {errors.primary_color && (
                  <p className="text-xs text-red-500 mt-1">{errors.primary_color}</p>
                )}
              </div>
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.position")}</label>
                <select value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 outline-none">
                  <option value="bottom-right">Bottom Right</option>
                  <option value="bottom-left">Bottom Left</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.greetingMessage")}</label>
              <input value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.suggestions")}</label>
              <input value={form.suggestions} onChange={(e) => setForm({ ...form, suggestions: e.target.value })}
                placeholder="What can you do?, Tell me about your products, How to get started?"
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
              <p className="text-xs text-gray-400 mt-1">{t("settings.suggestionsHint")}</p>
            </div>
          </div>
        </div>

        <button type="submit" disabled={mutation.isPending || Object.keys(errors).length > 0}
          className="flex items-center gap-2 bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50">
          <Save className="w-4 h-4" />
          {mutation.isPending ? t("settings.saving") : t("settings.saveChanges")}
        </button>
      </form>

      {/* Danger Zone — Delete Site */}
      <div className="mt-10 bg-white p-6 rounded-xl border-2 border-red-200">
        <h3 className="font-semibold text-red-700 mb-2">{t("settings.dangerZone")}</h3>
        <p className="text-sm text-gray-600 mb-4">{t("settings.deleteSiteDesc")}</p>

        {showDeleteConfirm ? (
          <div className="bg-red-50 p-4 rounded-lg border border-red-100">
            <p className="text-sm text-red-700 mb-3">{t("settings.deleteSiteConfirm")}</p>
            <div className="flex gap-3">
              <button
                onClick={() => deletesMutation.mutate()}
                disabled={deletesMutation.isPending}
                className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium"
              >
                <Trash2 className="w-4 h-4" />
                {deletesMutation.isPending ? t("settings.deleting") : t("settings.deleteSiteButton")}
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="text-gray-500 px-4 py-2 text-sm hover:text-gray-700"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="flex items-center gap-2 border-2 border-red-300 text-red-600 px-4 py-2 rounded-lg hover:bg-red-50 text-sm font-medium"
          >
            <Trash2 className="w-4 h-4" />
            {t("settings.deleteSite")}
          </button>
        )}
      </div>
    </div>
  );
}


function LLMKeysSection({ providers }: { providers: any[] }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const { data: savedKeys = [] } = useQuery({
    queryKey: ["llm-keys"],
    queryFn: getLLMKeys,
  });

  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);

  const saveMutation = useMutation({
    mutationFn: (data: { provider: string; api_key: string }) => saveLLMKey(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-keys"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      setEditingProvider(null);
      setKeyInput("");
      toast.success(t("settings.keySaved"));
    },
    onError: () => toast.error(t("settings.keyFailed")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteLLMKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llm-keys"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      toast.success(t("settings.keyDeleted"));
    },
  });

  const keyProviders = providers.filter((p: any) => p.requires_key);

  const getKeyInfo = (providerId: string) =>
    savedKeys.find((k: any) => k.provider === providerId);

  return (
    <div className="bg-white p-6 rounded-xl border border-gray-200">
      <div className="flex items-center gap-2 mb-4">
        <Key className="w-4 h-4 text-gray-500" />
        <h3 className="font-semibold">{t("settings.apiKeys")}</h3>
      </div>
      <p className="text-xs text-gray-500 mb-4">{t("settings.apiKeysDesc")}</p>

      <div className="space-y-3">
        {keyProviders.map((provider: any) => {
          const keyInfo = getKeyInfo(provider.id);
          const isEditing = editingProvider === provider.id;

          return (
            <div key={provider.id} className="border border-gray-100 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{provider.name}</span>
                  {keyInfo ? (
                    <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <Check className="w-3 h-3" /> {t("settings.keyConfigured")}
                    </span>
                  ) : (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                      {t("settings.keyNotSet")}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {keyInfo && !isEditing && (
                    <button
                      onClick={() => deleteMutation.mutate(provider.id)}
                      className="text-xs text-red-500 hover:text-red-700 px-2 py-1"
                    >
                      {t("common.delete")}
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (isEditing) {
                        setEditingProvider(null);
                        setKeyInput("");
                      } else {
                        setEditingProvider(provider.id);
                        setKeyInput("");
                        setShowKey(false);
                      }
                    }}
                    className="text-xs text-primary-600 hover:text-primary-700 px-2 py-1 font-medium"
                  >
                    {isEditing ? t("common.cancel") : keyInfo ? t("common.edit") : t("settings.addKey")}
                  </button>
                </div>
              </div>

              {keyInfo && !isEditing && (
                <p className="text-xs text-gray-400 mt-1 font-mono">{keyInfo.api_key_masked}</p>
              )}

              {isEditing && (
                <div className="mt-3 flex gap-2">
                  <div className="flex-1 relative">
                    <input
                      type={showKey ? "text" : "password"}
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={`${provider.id === "claude" ? "sk-ant-api03-..." : provider.id === "openai" ? "sk-..." : "AI..."}`}
                      className="w-full border rounded-lg px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-primary-500 pr-8"
                    />
                    <button
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <button
                    onClick={() => saveMutation.mutate({ provider: provider.id, api_key: keyInput })}
                    disabled={!keyInput || saveMutation.isPending}
                    className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50"
                  >
                    {t("common.save")}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
