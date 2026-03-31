import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getLLMKeys, saveLLMKey, deleteLLMKey, type Provider } from "../lib/api";
import { Key, Eye, EyeOff, Check } from "lucide-react";
import { useLocale } from "../lib/useLocale";

function getKeyBadge(provider: Provider, t: (key: string) => string) {
  if (!provider.has_key) {
    return {
      label: t("settings.keyNotSet"),
      className: "bg-gray-100 text-gray-500",
      showIcon: false,
    };
  }

  switch (provider.key_status) {
    case "working":
      return {
        label: t("settings.keyWorking"),
        className: "bg-green-50 text-green-700",
        showIcon: true,
      };
    case "invalid":
      return {
        label: t("settings.keyInvalid"),
        className: "bg-red-50 text-red-700",
        showIcon: false,
      };
    default:
      return {
        label: t("settings.keyConfigured"),
        className: "bg-amber-50 text-amber-700",
        showIcon: false,
      };
  }
}

export function LLMKeysSection({ providers }: { providers: Provider[] }) {
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

  const keyProviders = providers.filter((p) => p.requires_key);

  const getKeyInfo = (providerId: string) =>
    savedKeys.find((k) => k.provider === providerId);

  return (
    <div className="bg-white p-6 rounded-xl border border-gray-200">
      <div className="flex items-center gap-2 mb-4">
        <Key className="w-4 h-4 text-gray-500" />
        <h3 className="font-semibold">{t("settings.apiKeys")}</h3>
      </div>
      <p className="text-xs text-gray-500 mb-4">{t("settings.apiKeysDesc")}</p>

      <div className="space-y-3">
        {keyProviders.map((provider) => {
          const keyInfo = getKeyInfo(provider.id);
          const isEditing = editingProvider === provider.id;
          const badge = getKeyBadge(provider, t);

          return (
            <div key={provider.id} className="border border-gray-100 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{provider.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full flex items-center gap-1 ${badge.className}`}>
                    {badge.showIcon && <Check className="w-3 h-3" />}
                    {badge.label}
                  </span>
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
