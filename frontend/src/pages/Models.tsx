import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  getModelsProviders,
  getCustomModels,
  addCustomModel,
  deleteCustomModel,
  type Provider,
  type CustomModel,
} from "../lib/api";
import { LLMKeysSection } from "../components/LLMKeysSection";
import { useLocale } from "../lib/useLocale";
import { Cpu, Plus, Trash2, X, ChevronDown, ChevronRight, Sparkles } from "lucide-react";

export default function Models() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [providerSelection, setProviderSelection] = useState("");
  const [customProviderName, setCustomProviderName] = useState("");
  const [newModel, setNewModel] = useState<CustomModel>({
    provider: "",
    model_id: "",
    model_name: "",
    description: "",
  });

  const resetAddForm = () => {
    setShowAddForm(false);
    setProviderSelection("");
    setCustomProviderName("");
    setNewModel({ provider: "", model_id: "", model_name: "", description: "" });
  };

  const { data: providers = [] } = useQuery({
    queryKey: ["models-providers"],
    queryFn: getModelsProviders,
  });

  const { data: customModels = [] } = useQuery({
    queryKey: ["custom-models"],
    queryFn: getCustomModels,
  });

  const addMutation = useMutation({
    mutationFn: addCustomModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models-providers"] });
      queryClient.invalidateQueries({ queryKey: ["custom-models"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      resetAddForm();
      toast.success(t("models.modelAdded"));
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || "Failed to add model";
      toast.error(msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ provider, modelId }: { provider: string; modelId: string }) =>
      deleteCustomModel(provider, modelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models-providers"] });
      queryClient.invalidateQueries({ queryKey: ["custom-models"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      toast.success(t("models.modelRemoved"));
    },
  });

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const provider = providerSelection === "__custom__" ? customProviderName.trim() : providerSelection;
    if (!provider || !newModel.model_id || !newModel.model_name) return;
    addMutation.mutate({ ...newModel, provider });
  };

  const toggleProvider = (id: string) => {
    setExpandedProvider(expandedProvider === id ? null : id);
  };

  const isCustomModel = (provider: string, modelId: string) =>
    customModels.some((cm) => cm.provider === provider && cm.model_id === modelId);

  const getProviderBadge = (provider: Provider) => {
    if (!provider.requires_key) {
      return {
        label: t("models.localProvider"),
        className: "bg-blue-50 text-blue-700",
      };
    }

    switch (provider.key_status) {
      case "working":
        return {
          label: t("models.keyWorking"),
          className: "bg-green-50 text-green-700",
        };
      case "invalid":
        return {
          label: t("models.keyInvalid"),
          className: "bg-red-50 text-red-700",
        };
      default:
        return {
          label: t("models.keyMissing"),
          className: "bg-gray-100 text-gray-500",
        };
    }
  };

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Cpu className="w-6 h-6 text-primary-600" />
          {t("models.title")}
        </h1>
        <button
          onClick={() => {
            if (showAddForm) {
              resetAddForm();
              return;
            }
            setShowAddForm(true);
          }}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 text-sm font-medium"
        >
          {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showAddForm ? t("common.cancel") : t("models.addModel")}
        </button>
      </div>
      <p className="text-gray-500 mb-6">{t("models.subtitle")}</p>

      {/* Add Custom Model Form */}
      {showAddForm && (
        <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary-500" />
            {t("models.addCustomModel")}
          </h3>
          <form onSubmit={handleAdd} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("models.provider")}</label>
                <select
                  value={providerSelection}
                  onChange={(e) => {
                    setProviderSelection(e.target.value);
                    if (e.target.value !== "__custom__") {
                      setCustomProviderName("");
                    }
                  }}
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">{t("models.selectProvider")}</option>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                  <option value="__custom__">{t("models.otherProvider")}</option>
                </select>
              </div>
              {providerSelection === "__custom__" && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t("models.providerName")}</label>
                  <input
                    value={customProviderName}
                    onChange={(e) => setCustomProviderName(e.target.value)}
                    placeholder="my-provider"
                    className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("models.modelId")}</label>
                <input
                  value={newModel.model_id}
                  onChange={(e) => setNewModel({ ...newModel, model_id: e.target.value })}
                  placeholder="gpt-4.1-mini"
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t("models.modelName")}</label>
                <input
                  value={newModel.model_name}
                  onChange={(e) => setNewModel({ ...newModel, model_name: e.target.value })}
                  placeholder="GPT-4.1 Mini"
                  className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("models.description")}</label>
              <input
                value={newModel.description}
                onChange={(e) => setNewModel({ ...newModel, description: e.target.value })}
                placeholder="Fast and affordable"
                className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <button
              type="submit"
              disabled={
                !(providerSelection === "__custom__" ? customProviderName.trim() : providerSelection) ||
                !newModel.model_id ||
                !newModel.model_name ||
                addMutation.isPending
              }
              className="bg-primary-600 text-white px-6 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-50 text-sm font-medium"
            >
              {addMutation.isPending ? t("common.loading") : t("models.addModel")}
            </button>
          </form>
        </div>
      )}

      {/* API Keys */}
      <div className="mb-6">
        <LLMKeysSection providers={providers} />
      </div>

      {/* Providers & Models List */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold">{t("models.availableModels")}</h3>
          <p className="text-xs text-gray-500 mt-1">{t("models.availableModelsDesc")}</p>
        </div>

        <div className="divide-y divide-gray-100">
          {providers.map((provider) => {
            const badge = getProviderBadge(provider);

            return (
              <div key={provider.id}>
              {/* Provider header */}
              <button
                onClick={() => toggleProvider(provider.id)}
                className="w-full flex items-center justify-between px-6 py-3 hover:bg-gray-50 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  {expandedProvider === provider.id ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                  <span className="font-medium text-sm">{provider.name}</span>
                  <span className="text-xs text-gray-400">{provider.models.length} models</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${badge.className}`}>
                    {badge.label}
                  </span>
                  {provider.requires_key && provider.has_key && provider.key_status === "invalid" && (
                    <span className="text-xs text-red-500">{t("models.keySavedButInvalid")}</span>
                  )}
                </div>
              </button>

              {/* Models list */}
              {expandedProvider === provider.id && (
                <div className="bg-gray-50 px-6 py-2">
                  <div className="space-y-1">
                    {provider.models.map((model) => (
                      <div
                        key={model.id}
                        className="flex items-center justify-between py-2 px-3 bg-white rounded-lg border border-gray-100"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <code className="text-sm font-mono text-gray-800">{model.id}</code>
                            {isCustomModel(provider.id, model.id) && (
                              <span className="text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">Custom</span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {model.name}{model.description ? ` — ${model.description}` : ""}
                          </p>
                        </div>
                        {isCustomModel(provider.id, model.id) && (
                          <button
                            onClick={() => deleteMutation.mutate({ provider: provider.id, modelId: model.id })}
                            className="text-red-400 hover:text-red-600 p-1 ml-2"
                            title={t("common.delete")}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              </div>
            );
          })}
        </div>

        {providers.length === 0 && (
          <div className="px-6 py-8 text-center text-gray-400 text-sm">
            {t("common.loading")}
          </div>
        )}
      </div>
    </div>
  );
}
