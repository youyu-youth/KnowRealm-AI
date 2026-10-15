import { useTranslation } from "react-i18next";
import type { TodayProgress } from "@/features/today/api/today";

export function TodayProgressSummary({
  progress,
}: {
  progress: TodayProgress;
}) {
  const { t } = useTranslation();
  const minutes = progress.remaining_estimated_minutes;
  return (
    <div className="shrink-0 px-4 py-3">
      <dl
        aria-label={t("today.progress.title")}
        className="text-label flex flex-wrap gap-x-6 gap-y-2"
      >
        {[
          ["completed", progress.completed_count],
          ["pending", progress.pending_count],
          ["overdue", progress.overdue_count],
          [
            progress.unestimated_count > 0 && minutes != null
              ? "knownEstimated"
              : "remaining",
            minutes == null
              ? t("today.progress.unestimated")
              : t("today.planTodos.minutes", { minutes }),
          ],
        ].map(([key, value]) => (
          <div key={key} className="flex items-baseline gap-2">
            <dt className="text-ink-muted">{t(`today.progress.${key}`)}</dt>
            <dd className="text-ink-strong font-semibold tabular-nums">
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <p className="text-label text-ink-muted mt-2">
        {t("today.progress.basis")}
        {progress.unestimated_count > 0
          ? ` · ${t("today.progress.unknownCount", { count: progress.unestimated_count })}`
          : null}
      </p>
    </div>
  );
}
