import type { components } from "@knowrealm/api-types";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

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
  return (
    <div role="status" className="bg-surface-subtle space-y-3 rounded-lg p-4">
      <h2 className="text-section">{t(`practice.status.${latest.status}`)}</h2>
      <p className="text-label text-ink-muted">
        {t("practice.revision", { revision: latest.requirements_revision })} ·{" "}
        {latest.id}
      </p>
      {latest.outcome ? (
        <p className="text-body">
          {t(`practice.outcome.${latest.outcome}`, {
            count: latest.target_count,
            related: latest.related_count,
          })}
        </p>
      ) : null}
      <p className="text-label text-ink-muted">
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
      {latest.error_code ? (
        <p className="text-body text-danger">
          {t(`errors.${latest.error_code}`, {
            defaultValue: t("practice.failed"),
          })}
        </p>
      ) : null}
      <ul className="text-body space-y-1">
        {latest.sources.map((source) => (
          <li key={source.record_id}>
            {source.title} ·{" "}
            {t("practice.related", { count: source.related_count })}
            {source.matching_basis?.length ? (
              <span>
                {" "}
                ·{" "}
                {source.matching_basis
                  .map((reason) => t(`practice.basis.${reason}`))
                  .join(" · ")}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {latest.suggestions.length ? (
        <div className="space-y-2">
          <h3 className="text-section">{t("practice.suggestions")}</h3>
          <p className="text-label text-ink-muted">
            {t("practice.suggestionHint")}
          </p>
          <ul className="text-body space-y-1">
            {latest.suggestions.map((source) => (
              <li key={source.record_id}>
                {source.title} ·{" "}
                {t("practice.related", { count: source.related_count })}
                {source.matching_basis?.length ? (
                  <span>
                    {" "}
                    ·{" "}
                    {source.matching_basis
                      .map((reason) => t(`practice.basis.${reason}`))
                      .join(" · ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {["PENDING", "RUNNING"].includes(latest.status) ? (
        <Button
          variant="outline"
          disabled={cancelPending}
          onClick={() => onCancel(latest.id)}
        >
          {t("practice.cancel")}
        </Button>
      ) : null}
    </div>
  );
}
