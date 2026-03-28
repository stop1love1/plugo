import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { getSites, createSite, updateSiteApproval } from "../lib/api";
import { Plus, Globe, ArrowRight, ShieldCheck, ShieldX, ExternalLink } from "lucide-react";
import { useLocale } from "../lib/useLocale";

export default function Sites() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useLocale();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showCreate) nameInputRef.current?.focus();
  }, [showCreate]);

  const { data: sites = [], isLoading } = useQuery({
    queryKey: ["sites"],
    queryFn: getSites,
  });

  const mutation = useMutation({
    mutationFn: createSite,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      setShowCreate(false);
      setName("");
      setUrl("");
      toast.success(t("sites.created"));
      navigate(`/site/${data.id}/setup`);
    },
    onError: () => toast.error(t("sites.createFailed")),
  });

  const approvalMutation = useMutation({
    mutationFn: ({ siteId, approve }: { siteId: string; approve: boolean }) =>
      updateSiteApproval(siteId, approve),
    onSuccess: (_, { approve }) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      toast.success(approve ? t("sites.approved") : t("sites.rejected"));
    },
    onError: () => toast.error(t("sites.approvalFailed")),
  });

  const validateUrl = (value: string) => {
    if (!value) { setUrlError(""); return; }
    try {
      new URL(value);
      setUrlError("");
    } catch {
      setUrlError(t("settings.invalidUrl"));
    }
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !url || urlError) return;
    mutation.mutate({ name, url });
  };

  const handleApproval = (e: React.MouseEvent, siteId: string, approve: boolean) => {
    e.stopPropagation();
    approvalMutation.mutate({ siteId, approve });
  };

  const handleOpenDemo = (e: React.MouseEvent, token: string) => {
    e.stopPropagation();
    window.open(`http://localhost:8000/demo/${token}`, "_blank");
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t("sites.title")}</h1>
          <p className="text-gray-500 mt-1">{t("sites.subtitle")}</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> {t("sites.addSite")}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
          <h3 className="font-semibold text-lg mb-4">{t("sites.addSite")}</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t("settings.websiteName")}</label>
              <input
                ref={nameInputRef}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Website"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
              <input
                value={url}
                onChange={(e) => { setUrl(e.target.value); validateUrl(e.target.value); }}
                placeholder="https://example.com"
                className={`w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none ${urlError ? "border-red-300" : "border-gray-300"}`}
              />
              {urlError && <p className="text-xs text-red-500 mt-1">{urlError}</p>}
            </div>
            <p className="text-xs text-amber-600 bg-amber-50 px-3 py-2 rounded-lg">
              {t("sites.approvalNote")}
            </p>
            <div className="flex gap-3">
              <button type="submit" disabled={mutation.isPending} className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700">
                {mutation.isPending ? t("common.loading") : t("sites.addSite")}
              </button>
              <button type="button" onClick={() => setShowCreate(false)} className="text-gray-500 px-4 py-2">
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="text-gray-400">{t("common.loading")}</div>
      ) : sites.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
          <Globe className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">{t("sites.noSites")}</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {sites.map((site: any) => (
            <div
              key={site.id}
              onClick={() => navigate(`/site/${site.id}/analytics`)}
              className="bg-white p-5 rounded-xl border border-gray-200 hover:border-primary-300 hover:shadow-sm cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{site.name}</h3>
                    {site.is_approved ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium bg-green-50 text-green-700 px-2 py-0.5 rounded-full">
                        <ShieldCheck className="w-3 h-3" />
                        {t("sites.statusApproved")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-medium bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full">
                        <ShieldX className="w-3 h-3" />
                        {t("sites.statusPending")}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{site.url}</p>
                  <p className="text-xs text-gray-400 mt-1">Token: {site.token.substring(0, 12)}...</p>
                </div>

                <div className="flex items-center gap-2 ml-4">
                  {/* Demo page link */}
                  <button
                    onClick={(e) => handleOpenDemo(e, site.token)}
                    className="text-xs text-gray-500 hover:text-primary-600 border border-gray-200 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                    title={t("sites.openDemo")}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Demo
                  </button>

                  {/* Approval toggle */}
                  {site.is_approved ? (
                    <button
                      onClick={(e) => handleApproval(e, site.id, false)}
                      className="text-xs text-red-600 hover:text-red-700 border border-red-200 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                      title={t("sites.revoke")}
                    >
                      <ShieldX className="w-3.5 h-3.5" />
                      {t("sites.revoke")}
                    </button>
                  ) : (
                    <button
                      onClick={(e) => handleApproval(e, site.id, true)}
                      className="text-xs text-green-600 hover:text-green-700 border border-green-200 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                      title={t("sites.approve")}
                    >
                      <ShieldCheck className="w-3.5 h-3.5" />
                      {t("sites.approve")}
                    </button>
                  )}

                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
