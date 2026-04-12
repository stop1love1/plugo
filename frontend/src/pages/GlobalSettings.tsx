import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Save, RotateCcw, Server, Brain, Database, Shield, Zap, Globe,
  Bot, AlertTriangle, Cpu, Bug,
} from "lucide-react";
import { getGlobalConfig, updateGlobalConfig, getErrorMessage } from "../lib/api";

type SectionConfig = Record<string, unknown>;

// ─── Reusable components ──────────────────────────────────────

function InputField({
  label, value, onChange, type = "text", placeholder, hint, disabled, mono,
}: {
  label: string; value: string | number; onChange: (v: string) => void;
  type?: string; placeholder?: string; hint?: string; disabled?: boolean; mono?: boolean;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type={type} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} disabled={disabled}
        className={`w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50 disabled:text-gray-400 ${mono ? "font-mono" : ""}`}
      />
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}

function TextAreaField({
  label, value, onChange, rows = 4, placeholder, hint, mono,
}: {
  label: string; value: string; onChange: (v: string) => void;
  rows?: number; placeholder?: string; hint?: string; mono?: boolean;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <textarea
        value={value} onChange={(e) => onChange(e.target.value)}
        rows={rows} placeholder={placeholder}
        className={`w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500 ${mono ? "font-mono text-xs leading-relaxed" : ""}`}
      />
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}

function SelectField({
  label, value, onChange, options, hint,
}: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[]; hint?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}

// ─── Tab definitions ──────────────────────────────────────────

const tabs = [
  { id: "ai", label: "AI & Prompts", icon: Bot },
  { id: "llm", label: "LLM & Models", icon: Cpu },
  { id: "embedding", label: "Embedding", icon: Zap },
  { id: "database", label: "Database", icon: Database },
  { id: "rag", label: "RAG Pipeline", icon: Brain },
  { id: "server", label: "Server", icon: Globe },
  { id: "crawl", label: "Crawl", icon: Bug },
  { id: "rate_limit", label: "Rate Limits", icon: Shield },
] as const;

type TabId = (typeof tabs)[number]["id"];

// ─── Main component ──────────────────────────────────────────

export default function GlobalSettings() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabId>("ai");

  const { data: config, isLoading } = useQuery({
    queryKey: ["global-config"],
    queryFn: getGlobalConfig,
  });

  const [form, setForm] = useState<Record<string, SectionConfig>>({});
  const [hasChanges, setHasChanges] = useState(false);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    if (config) {
      setForm(structuredClone(config));
      setHasChanges(false);
    }
  }, [config]);

  const update = (section: string, key: string, value: unknown) => {
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }));
    setHasChanges(true);
  };

  const get = (section: string, key: string, fallback: unknown = "") => {
    return (form[section]?.[key] ?? fallback) as never;
  };

  const mutation = useMutation({
    mutationFn: updateGlobalConfig,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["global-config"] });
      setHasChanges(false);
      toast.success(data.message || "Settings saved");
    },
    onError: (error) => toast.error(getErrorMessage(error)),
  });

  const handleSave = useCallback(() => {
    if (!config) return;
    const changes: Record<string, SectionConfig> = {};
    for (const [section, values] of Object.entries(form)) {
      if (JSON.stringify(values) !== JSON.stringify(config[section])) {
        changes[section] = values;
      }
    }
    if (Object.keys(changes).length === 0) { toast("No changes"); return; }
    mutation.mutate(changes);
  }, [config, form, mutation]);

  const handleReset = () => {
    if (config) { setForm(structuredClone(config)); setHasChanges(false); }
  };

  const scrollToSection = (id: TabId) => {
    setActiveTab(id);
    sectionRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Ctrl+S
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (hasChanges) handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [hasChanges, handleSave]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex gap-6 -m-4 lg:-m-8 min-h-screen">
      {/* Sidebar nav */}
      <div className="w-52 shrink-0 bg-white border-r border-gray-200 p-4 sticky top-0 h-screen overflow-y-auto">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3 px-2">Settings</h2>
        <nav className="space-y-0.5">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => scrollToSection(id)}
              className={`flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg text-sm transition-colors ${
                activeTab === id
                  ? "bg-primary-50 text-primary-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        {/* Save in sidebar */}
        <div className="mt-6 pt-4 border-t border-gray-200 space-y-2">
          <button
            onClick={handleSave}
            disabled={!hasChanges || mutation.isPending}
            className="flex items-center justify-center gap-2 w-full bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm font-medium"
          >
            <Save className="w-4 h-4" />
            {mutation.isPending ? "Saving..." : "Save"}
          </button>
          {hasChanges && (
            <button onClick={handleReset}
              className="flex items-center justify-center gap-2 w-full text-gray-500 hover:text-gray-700 px-4 py-2 text-sm">
              <RotateCcw className="w-4 h-4" /> Discard
            </button>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 py-6 pr-6 max-w-5xl space-y-8 overflow-y-auto">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Global Settings</h1>
          <p className="text-gray-500 text-sm mt-1">System-wide configuration for all sites. Some changes require a server restart.</p>
        </div>

        {hasChanges && (
          <div className="px-4 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Unsaved changes — <kbd className="px-1.5 py-0.5 bg-amber-100 rounded text-xs font-mono">Ctrl+S</kbd> to save
          </div>
        )}

        {/* ─── AI & Prompts ─── */}
        <div ref={(el) => { sectionRefs.current["ai"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Bot} title="AI & System Prompts" desc="Global system prompt template and fallback responses. Per-site custom prompts are appended after this.">
            <TextAreaField
              label="System Prompt Template"
              value={get("agent", "system_prompt", "")}
              onChange={(v) => update("agent", "system_prompt", v)}
              rows={16}
              mono
              placeholder="Leave empty to use default built-in prompt. Supports {site_name}, {site_url}, {memory_section}, {context_section}, {knowledge_section}, {tools_section} placeholders."
              hint="The master prompt sent to the LLM for every chat. Leave empty to use the built-in default. Must include {site_name}, {site_url}, {knowledge_section}, {tools_section} placeholders."
            />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <TextAreaField
                label="No-Knowledge Response (Vietnamese)"
                value={get("agent", "no_knowledge_response_vi", "")}
                onChange={(v) => update("agent", "no_knowledge_response_vi", v)}
                rows={3}
                placeholder="Leave empty for default: 'Xin lỗi, mình chưa có thông tin...'"
                hint="Shown when no relevant knowledge is found and user speaks Vietnamese"
              />
              <TextAreaField
                label="No-Knowledge Response (English)"
                value={get("agent", "no_knowledge_response_en", "")}
                onChange={(v) => update("agent", "no_knowledge_response_en", v)}
                rows={3}
                placeholder="Leave empty for default: 'I'm sorry, I don't have information...'"
                hint="Shown when no relevant knowledge is found and user speaks English"
              />
            </div>
            <InputField
              label="No-Tool Providers"
              value={Array.isArray(get("agent", "no_tool_providers")) ? (get("agent", "no_tool_providers") as string[]).join(", ") : String(get("agent", "no_tool_providers", ""))}
              onChange={(v) => update("agent", "no_tool_providers", v.split(",").map((s: string) => s.trim()).filter(Boolean))}
              placeholder="ollama, lmstudio"
              hint="Comma-separated list of providers that don't support function/tool calling"
            />
          </SectionCard>
        </div>

        {/* ─── LLM & Models ─── */}
        <div ref={(el) => { sectionRefs.current["llm"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Cpu} title="Default LLM" desc="Default model for new sites. Each site can override in its own settings.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="Provider" value={get("llm", "provider", "claude")} onChange={(v) => update("llm", "provider", v)} placeholder="claude" hint="claude, openai, gemini, ollama, lmstudio" />
              <InputField label="Model" value={get("llm", "model", "")} onChange={(v) => update("llm", "model", v)} placeholder="claude-sonnet-4-20250514" />
            </div>
          </SectionCard>
          <div className="mt-4">
            <SectionCard icon={Server} title="Ollama / Local Models" desc="Settings for locally hosted LLM servers.">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <InputField label="Ollama Base URL" value={get("ollama", "base_url", "http://localhost:11434")} onChange={(v) => update("ollama", "base_url", v)} placeholder="http://localhost:11434" />
                <InputField label="Default Ollama Model" value={get("ollama", "model", "llama3")} onChange={(v) => update("ollama", "model", v)} placeholder="llama3" />
              </div>
            </SectionCard>
          </div>
        </div>

        {/* ─── Embedding ─── */}
        <div ref={(el) => { sectionRefs.current["embedding"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Zap} title="Embedding" desc="Vector embeddings for knowledge base search (RAG). Restart required after changes.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="Provider" value={get("embedding", "provider", "openai")} onChange={(v) => update("embedding", "provider", v)} placeholder="openai" hint="openai, gemini, ollama" />
              <InputField label="Model" value={get("embedding", "model", "")} onChange={(v) => update("embedding", "model", v)} placeholder="text-embedding-3-small" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="Cache Size" type="number" value={get("embedding", "cache_size", 1000)} onChange={(v) => update("embedding", "cache_size", parseInt(v) || 1000)} hint="Number of embeddings cached in memory" />
              <InputField label="Cache TTL (seconds)" type="number" value={get("embedding", "cache_ttl", 3600)} onChange={(v) => update("embedding", "cache_ttl", parseInt(v) || 3600)} />
            </div>
          </SectionCard>
        </div>

        {/* ─── Database ─── */}
        <div ref={(el) => { sectionRefs.current["database"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Database} title="Database" desc="Primary data store. Changing provider requires a server restart.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <SelectField label="Provider" value={get("database", "provider", "sqlite")} onChange={(v) => update("database", "provider", v)}
                options={[{ value: "sqlite", label: "SQLite" }, { value: "mongodb", label: "MongoDB" }]} />
              <InputField label="SQLite URL" value={get("database", "url", "")} onChange={(v) => update("database", "url", v)} disabled={get("database", "provider") !== "sqlite"} mono />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="MongoDB URL" value={get("database", "mongodb_url", "")} onChange={(v) => update("database", "mongodb_url", v)} disabled={get("database", "provider") !== "mongodb"} placeholder="mongodb://localhost:27017" mono />
              <InputField label="MongoDB Database" value={get("database", "mongodb_database", "")} onChange={(v) => update("database", "mongodb_database", v)} disabled={get("database", "provider") !== "mongodb"} placeholder="plugo" />
            </div>
          </SectionCard>
        </div>

        {/* ─── RAG ─── */}
        <div ref={(el) => { sectionRefs.current["rag"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Brain} title="RAG Pipeline" desc="Controls how knowledge base search retrieves and ranks content.">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InputField label="Min Score" type="number" value={get("rag", "min_score", 0.3)} onChange={(v) => update("rag", "min_score", parseFloat(v) || 0.3)} hint="Minimum relevance (0-1)" />
              <InputField label="Max Chunks" type="number" value={get("rag", "max_chunks", 7)} onChange={(v) => update("rag", "max_chunks", parseInt(v) || 7)} hint="Max context chunks" />
              <InputField label="ChromaDB Path" value={get("vector_store", "chroma_path", "./data/chroma")} onChange={(v) => update("vector_store", "chroma_path", v)} mono />
            </div>
          </SectionCard>
        </div>

        {/* ─── Server ─── */}
        <div ref={(el) => { sectionRefs.current["server"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Globe} title="Server & Network" desc="Backend port, CORS, and widget delivery. Restart required.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InputField label="Backend Port" type="number" value={get("server", "backend_port", 8000)} onChange={(v) => update("server", "backend_port", parseInt(v) || 8000)} />
              <InputField label="Widget CDN URL" value={get("server", "widget_cdn_url", "")} onChange={(v) => update("server", "widget_cdn_url", v)} hint="Public URL to widget.js" mono />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">CORS Origins</label>
              <textarea
                value={Array.isArray(get("server", "cors_origins")) ? (get("server", "cors_origins") as string[]).join("\n") : String(get("server", "cors_origins", ""))}
                onChange={(e) => update("server", "cors_origins", e.target.value.split("\n").map((s: string) => s.trim()).filter(Boolean))}
                rows={3} placeholder={"http://localhost:3000\nhttp://localhost:5173"}
                className="w-full border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary-500 font-mono"
              />
              <p className="text-xs text-gray-400 mt-1">One origin per line</p>
            </div>
          </SectionCard>
        </div>

        {/* ─── Crawl ─── */}
        <div ref={(el) => { sectionRefs.current["crawl"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Bug} title="Crawl Defaults" desc="Default crawling behavior for all sites.">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <SelectField label="Verify SSL" value={get("crawl", "verify_ssl", true) ? "true" : "false"} onChange={(v) => update("crawl", "verify_ssl", v === "true")}
                options={[{ value: "true", label: "Yes" }, { value: "false", label: "No" }]} />
              <InputField label="Request Delay (sec)" type="number" value={get("crawl", "request_delay", 1.0)} onChange={(v) => update("crawl", "request_delay", parseFloat(v) || 1.0)} />
              <InputField label="Request Timeout (sec)" type="number" value={get("crawl", "request_timeout", 30)} onChange={(v) => update("crawl", "request_timeout", parseInt(v) || 30)} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InputField label="Max Concurrent Fetches" type="number" value={get("crawl", "max_concurrent_fetches", 5)} onChange={(v) => update("crawl", "max_concurrent_fetches", parseInt(v) || 5)} />
              <InputField label="Max Auto Crawls" type="number" value={get("crawl", "max_concurrent_auto_crawls", 3)} onChange={(v) => update("crawl", "max_concurrent_auto_crawls", parseInt(v) || 3)} />
              <InputField label="Embed Batch Size" type="number" value={get("crawl", "embed_batch_size", 200)} onChange={(v) => update("crawl", "embed_batch_size", parseInt(v) || 200)} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InputField label="Scheduler Interval (sec)" type="number" value={get("crawl", "scheduler_interval_seconds", 300)} onChange={(v) => update("crawl", "scheduler_interval_seconds", parseInt(v) || 300)} />
              <InputField label="Max Retries" type="number" value={get("crawl", "max_retries", 2)} onChange={(v) => update("crawl", "max_retries", parseInt(v) || 2)} />
              <InputField label="Stale Timeout (min)" type="number" value={get("crawl", "stale_timeout_minutes", 30)} onChange={(v) => update("crawl", "stale_timeout_minutes", parseInt(v) || 30)} />
            </div>
            <InputField label="Max Continuous Rounds" type="number" value={get("crawl", "max_continuous_rounds", 10)} onChange={(v) => update("crawl", "max_continuous_rounds", parseInt(v) || 10)}
              hint="Maximum consecutive auto-crawl rounds before pausing" />
          </SectionCard>
        </div>

        {/* ─── Rate Limits ─── */}
        <div ref={(el) => { sectionRefs.current["rate_limit"] = el; }} className="scroll-mt-6">
          <SectionCard icon={Shield} title="Rate Limiting" desc="Request limits per endpoint. Format: count/period (e.g. 60/minute, 10/second).">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InputField label="Default" value={get("rate_limit", "default", "60/minute")} onChange={(v) => update("rate_limit", "default", v)} placeholder="60/minute" />
              <InputField label="Chat" value={get("rate_limit", "chat", "30/minute")} onChange={(v) => update("rate_limit", "chat", v)} placeholder="30/minute" />
              <InputField label="Crawl" value={get("rate_limit", "crawl", "5/minute")} onChange={(v) => update("rate_limit", "crawl", v)} placeholder="5/minute" />
            </div>
          </SectionCard>
        </div>

        {/* Bottom spacer */}
        <div className="h-8" />
      </div>
    </div>
  );
}

// ─── Section card ────────────────────────────────────────────

function SectionCard({
  icon: Icon, title, desc, children,
}: {
  icon: React.ElementType; title: string; desc?: string; children: React.ReactNode;
}) {
  return (
    <div className="bg-white p-6 rounded-xl border border-gray-200">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-5 h-5 text-primary-600" />
        <h3 className="font-semibold text-gray-900">{title}</h3>
      </div>
      {desc && <p className="text-xs text-gray-400 mb-4">{desc}</p>}
      {!desc && <div className="mb-4" />}
      <div className="space-y-4">{children}</div>
    </div>
  );
}
