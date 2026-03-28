import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSite, getSessions } from "../lib/api";
import { Check, Circle, ArrowRight } from "lucide-react";
import { useLocale } from "../lib/useLocale";
import api from "../lib/api";

const getCrawlStatus = (siteId: string) =>
  api.get(`/crawl/status/${siteId}`).then((r) => r.data);

export function OnboardingChecklist() {
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  const { t } = useLocale();

  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: crawlStatus } = useQuery({
    queryKey: ["crawl-status", siteId],
    queryFn: () => getCrawlStatus(siteId!),
    enabled: !!siteId,
  });

  // Check if widget has been embedded by looking for sessions
  const { data: sessions } = useQuery({
    queryKey: ["sessions", siteId],
    queryFn: () => getSessions(siteId!),
    enabled: !!siteId,
  });

  const hasEmbedded = Array.isArray(sessions) && sessions.length > 0;

  if (!site || !siteId) return null;

  const steps = [
    {
      key: "create",
      label: t("onboarding.step1"),
      done: true,
      action: null,
    },
    {
      key: "llm",
      label: t("onboarding.step2"),
      done: !!site.llm_provider && !!site.llm_model,
      action: () => navigate(`/site/${siteId}/settings`),
      actionLabel: t("onboarding.goToSettings"),
    },
    {
      key: "knowledge",
      label: t("onboarding.step3"),
      done: (crawlStatus?.knowledge_count ?? 0) > 0,
      action: () => navigate(`/site/${siteId}/setup`),
      actionLabel: t("onboarding.goToSetup"),
    },
    {
      key: "widget",
      label: t("onboarding.step4"),
      done: !!site.primary_color && !!site.greeting,
      action: () => navigate(`/site/${siteId}/settings`),
      actionLabel: t("onboarding.goToSettings"),
    },
    {
      key: "embed",
      label: t("onboarding.step5"),
      done: hasEmbedded,
      action: () => navigate(`/site/${siteId}/embed`),
      actionLabel: t("onboarding.goToEmbed"),
    },
  ];

  const completedCount = steps.filter((s) => s.done).length;
  const allDone = completedCount === steps.length;
  const progressPercent = Math.round((completedCount / steps.length) * 100);

  // Don't show if most steps are done
  if (completedCount >= 4) return null;

  return (
    <div className="bg-white p-5 rounded-xl border border-gray-200 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900">{t("onboarding.title")}</h3>
        <span className="text-xs text-gray-500">{completedCount}/{steps.length}</span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-1.5 mb-4">
        <div
          className="bg-primary-600 h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <div className="space-y-2">
        {steps.map((step) => (
          <div
            key={step.key}
            className={`flex items-center justify-between p-2 rounded-lg ${
              step.done ? "bg-green-50" : "bg-gray-50"
            }`}
          >
            <div className="flex items-center gap-2">
              {step.done ? (
                <Check className="w-4 h-4 text-green-600" />
              ) : (
                <Circle className="w-4 h-4 text-gray-300" />
              )}
              <span className={`text-sm ${step.done ? "text-green-700 line-through" : "text-gray-700"}`}>
                {step.label}
              </span>
            </div>
            {!step.done && step.action && (
              <button
                onClick={step.action}
                className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
              >
                {step.actionLabel}
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
