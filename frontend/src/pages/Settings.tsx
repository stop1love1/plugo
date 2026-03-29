import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getSite, updateSite, deleteSite, getModelsProviders, type UpdateSiteData } from "../lib/api";
import { Save, Trash2, AlertTriangle } from "lucide-react";
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
    queryKey: ["models-providers"],
    queryFn: getModelsProviders,
  });

  const [form, setForm] = useState({
    name: "",
    url: "",
    llm_provider: "",
    llm_model: "",
    primary_color: "#6366f1",
    greeting: "",
    position: "bottom-right",
    widget_title: "",
    dark_mode: "auto",
    bot_avatar: "",
    header_subtitle: "",
    input_placeholder: "",
    auto_open_delay: 0,
    bubble_size: "medium",
    allowed_domains: "",
    suggestions: "",
    system_prompt: "",
    bot_rules: "",
  });

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (site) {
      setForm({
        name: site.name,
        url: site.url || "",
        llm_provider: site.llm_provider,
        llm_model: site.llm_model,
        primary_color: site.primary_color,
        greeting: site.greeting,
        position: site.position,
        widget_title: site.widget_title || "",
        dark_mode: site.dark_mode || "auto",
        bot_avatar: site.bot_avatar || "",
        header_subtitle: site.header_subtitle || "",
        input_placeholder: site.input_placeholder || "",
        auto_open_delay: site.auto_open_delay || 0,
        bubble_size: site.bubble_size || "medium",
        allowed_domains: site.allowed_domains,
        suggestions: (site.suggestions || []).join(", "),
        system_prompt: site.system_prompt || "",
        bot_rules: site.bot_rules || "",
      });
    }
  }, [site]);

  // Track unsaved changes
  const hasChanges = useMemo(() => {
    if (!site) return false;
    return (
      form.name !== site.name ||
      form.url !== (site.url || "") ||
      form.llm_provider !== site.llm_provider ||
      form.llm_model !== site.llm_model ||
      form.primary_color !== site.primary_color ||
      form.greeting !== site.greeting ||
      form.position !== site.position ||
      form.widget_title !== (site.widget_title || "") ||
      form.dark_mode !== (site.dark_mode || "auto") ||
      form.bot_avatar !== (site.bot_avatar || "") ||
      form.header_subtitle !== (site.header_subtitle || "") ||
      form.input_placeholder !== (site.input_placeholder || "") ||
      form.auto_open_delay !== (site.auto_open_delay || 0) ||
      form.bubble_size !== (site.bubble_size || "medium") ||
      form.allowed_domains !== site.allowed_domains ||
      form.suggestions !== (site.suggestions || []).join(", ") ||
      form.system_prompt !== (site.system_prompt || "") ||
      form.bot_rules !== (site.bot_rules || "")
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
    mutationFn: (data: UpdateSiteData) => updateSite(siteId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["site", siteId] });
      toast.success("Settings saved");
    },
    onError: () => toast.error("Failed to save settings"),
  });

  // Ctrl+S / Cmd+S keyboard shortcut to save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (hasChanges && Object.keys(errors).length === 0) {
          const { suggestions: suggestionsStr, ...rest } = form;
          const suggestions = suggestionsStr
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
          mutation.mutate({ ...rest, suggestions });
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [hasChanges, form, errors, mutation]);

  // Prevent navigate-away with unsaved changes
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (hasChanges) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasChanges]);

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

  const currentProvider = providers.find((p) => p.id === form.llm_provider);

  // Build flat list of all models grouped by provider for display
  const allModels = providers.flatMap((p) =>
    p.models.map((m) => ({ ...m, provider_id: p.id, provider_name: p.name }))
  );

  return (
    <div>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.websiteUrl")}</label>
              <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://example.com"
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
              <p className="text-xs text-gray-400 mt-1">{t("settings.websiteUrlHint")}</p>
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

        {/* Model Selection — simplified */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">{t("settings.model")}</h3>
            <a href="/models" className="text-xs text-primary-600 hover:text-primary-700 font-medium">
              {t("settings.manageModels")} &rarr;
            </a>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.provider")}</label>
              <select value={form.llm_provider} onChange={(e) => {
                const p = providers.find((p) => p.id === e.target.value);
                setForm({
                  ...form,
                  llm_provider: e.target.value,
                  llm_model: p?.models?.[0]?.id || "",
                });
              }} className="w-full border rounded-lg px-3 py-2 outline-none">
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.model")}</label>
              <select value={form.llm_model} onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none">
                {currentProvider?.models?.map((m) => (
                  <option key={m.id} value={m.id}>{m.name} — {m.description}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* AI Rules & Instructions */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("settings.aiRules")}</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.systemPrompt")}</label>
              <textarea
                value={form.system_prompt}
                onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                placeholder={t("settings.systemPromptPlaceholder")}
                rows={3}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 text-sm"
              />
              <p className="text-xs text-gray-400 mt-1">{t("settings.systemPromptHint")}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.botRules")}</label>
              <textarea
                value={form.bot_rules}
                onChange={(e) => setForm({ ...form, bot_rules: e.target.value })}
                placeholder={t("settings.botRulesPlaceholder")}
                rows={5}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500 text-sm font-mono"
              />
              <p className="text-xs text-gray-400 mt-1">{t("settings.botRulesHint")}</p>
            </div>
          </div>
        </div>

        {/* Widget — Appearance */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("settings.widget")} — Appearance</h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.position")}</label>
                <select value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 outline-none">
                  <option value="bottom-right">Bottom Right</option>
                  <option value="bottom-left">Bottom Left</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dark Mode</label>
                <select value={form.dark_mode} onChange={(e) => setForm({ ...form, dark_mode: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 outline-none">
                  <option value="auto">Auto (follow system)</option>
                  <option value="light">Always Light</option>
                  <option value="dark">Always Dark</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bot Avatar</label>
                <input value={form.bot_avatar} onChange={(e) => setForm({ ...form, bot_avatar: e.target.value })}
                  placeholder="🤖"
                  maxLength={4}
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
                <p className="text-xs text-gray-400 mt-1">Emoji hiển thị trong header và tin nhắn bot</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Bubble Size</label>
                <select value={form.bubble_size} onChange={(e) => setForm({ ...form, bubble_size: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 outline-none">
                  <option value="small">Small (48px)</option>
                  <option value="medium">Medium (56px)</option>
                  <option value="large">Large (64px)</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Widget — Content */}
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <h3 className="font-semibold mb-4">{t("settings.widget")} — Content</h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Widget Title</label>
                <input value={form.widget_title} onChange={(e) => setForm({ ...form, widget_title: e.target.value })}
                  placeholder="Chat with us"
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Header Subtitle</label>
                <input value={form.header_subtitle} onChange={(e) => setForm({ ...form, header_subtitle: e.target.value })}
                  placeholder="Online"
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.greetingMessage")}</label>
              <input value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })}
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Input Placeholder</label>
                <input value={form.input_placeholder} onChange={(e) => setForm({ ...form, input_placeholder: e.target.value })}
                  placeholder="Type a message..."
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Auto Open (seconds)</label>
                <input type="number" min={0} max={120} value={form.auto_open_delay}
                  onChange={(e) => setForm({ ...form, auto_open_delay: parseInt(e.target.value) || 0 })}
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500" />
                <p className="text-xs text-gray-400 mt-1">0 = tắt. Tự mở widget sau N giây khi user vào trang</p>
              </div>
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
          title="Ctrl+S"
          className="flex items-center gap-2 bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50">
          <Save className="w-4 h-4" />
          {mutation.isPending ? t("settings.saving") : t("settings.saveChanges")}
          <kbd className="ml-1 text-xs bg-primary-700 px-1.5 py-0.5 rounded opacity-75">Ctrl+S</kbd>
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
