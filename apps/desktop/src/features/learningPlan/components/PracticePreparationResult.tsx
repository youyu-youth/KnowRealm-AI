import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { PracticeSourceList } from "@/features/learningPlan/components/PracticeSourceList";
import { Check, Clock3, TriangleAlert } from "lucide-react";

export function PracticePreparationResult({
  latest,
  cancelPending,
  onCancel,
}: {
  latest: components["schemas"]["PracticePreparationOut"];
  cancelPending: boolean;
  onCancel: (id: string) => void;
}) {
  const { t } = useTranslation();
  const active = ["PENDING", "RUNNING"].includes(latest.status);
  const Icon = active
    ? Clock3
    : latest.outcome === "READY"
      ? Check
      : TriangleAlert;
  return (
    <section
      aria-label={t("practice.workspace.matching")}
      className="space-y-4 py-2"
    >
      <div role="status" className="flex items-start gap-3">
        <Icon
          aria-hidden="true"
          className={`mt-0.5 size-4 shrink-0 ${latest.outcome === "READY" ? "text-success-foreground" : active || latest.status === "CANCELLED" ? "text-ink-muted" : "text-warning-foreground"}`}
        />
        <div className="min-w-0 space-y-2">
          <h2 className="text-body text-ink font-semibold">
            {t(`practice.status.${latest.status}`)}
          </h2>
          {latest.outcome ? (
            <p className="text-body">
              {t(`practice.outcome.${latest.outcome}`, {
                count: latest.target_count,
                related: latest.related_count,
              })}
            </p>
          ) : null}
        </div>
      </div>
      {latest.reused_count > 0 ? (
        <p className="text-body text-ink-muted">
          {t("practice.recovery.reused", { count: latest.reused_count })}
        </p>
      ) : null}
      {latest.error_code ? (
        <p role="alert" className="text-body text-danger">
          {t(`errors.${latest.error_code}`, {
            defaultValue: t("practice.failed"),
          })}
        </p>
      ) : null}
      <details
        key={latest.id}
        className="practice-disclosure"
        open={latest.outcome === "INSUFFICIENT" || latest.status === "FAILED"}
      >
        <summary>{t("practice.workspace.matchDetails")}</summary>
        <div className="mt-4 space-y-4">
          <p className="text-label text-ink-muted tabular-nums">
            {t("practice.scanned", {
              examined: latest.examined_count,
              total: latest.total_candidates,
            })}{" "}
            ·{" "}
            {t(
              latest.course_scan_complete
                ? "practice.scanComplete"
                : "practice.scanPartial",
            )}
          </p>
          <PracticeSourceList sources={latest.sources} />
          <div className="text-label text-ink-muted space-y-1">
            <p>
              {t("practice.revision", {
                revision: latest.requirements_revision,
              })}
            </p>
            <p className="wrap-anywhere select-all">
              {t("practice.workspace.matchId", { id: latest.id })}
            </p>
          </div>
        </div>
      </details>
      {latest.suggestions.length ? (
        <div className="space-y-2">
          <h3 className="text-section">{t("practice.suggestions")}</h3>
          <p className="text-label text-ink-muted">
            {t("practice.suggestionHint")}
          </p>
          <PracticeSourceList sources={latest.suggestions} />
        </div>
      ) : null}
      {active ? (
        <Button
          variant="outline"
          disabled={cancelPending}
          onClick={() => onCancel(latest.id)}
        >
          {t("practice.cancel")}
        </Button>
      ) : null}
    </section>
  );
}
