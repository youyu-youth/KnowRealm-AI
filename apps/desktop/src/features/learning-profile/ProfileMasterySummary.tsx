import { useTranslation } from "react-i18next";
import type {
  CourseMastery,
  MasteryStatus,
} from "@/features/courses/api/types";
import {
  masteryStatusCountKeys,
  masteryStatusLabelKeys,
  masteryDotCssVars,
} from "@/features/courses/masteryStatus";
import { BaseChart } from "@/charts/BaseChart";
import { cssVar } from "@/charts/token";
import { useAppearanceSnapshot } from "@/hooks/useAppearanceSnapshot";
import { cn } from "@/lib/utils";

const displayStatuses: MasteryStatus[] = [
  "STABLE",
  "LEARNING",
  "WEAK",
  "NOT_ENOUGH_DATA",
];

export function ProfileMasterySummary({
  data,
  selected,
  onSelect,
}: {
  data: CourseMastery;
  selected?: MasteryStatus;
  onSelect: (status?: MasteryStatus) => void;
}) {
  const { t } = useTranslation();
  useAppearanceSnapshot();
  const option = {
    animation: false,
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: {
      type: "value",
      show: false,
      max: data.confirmed_concept_count || 1,
    },
    yAxis: { type: "category", show: false, data: [""] },
    series: displayStatuses.map((status) => ({
      type: "bar",
      stack: "mastery",
      silent: true,
      barWidth: "100%",
      data: [data.status_counts[masteryStatusCountKeys[status]]],
      itemStyle: {
        color: cssVar(masteryDotCssVars[status]),
        borderColor: cssVar("--paper"),
        borderWidth: 1,
      },
    })),
  };
  return (
    <section
      aria-label={t("learningProfile.mastery.title")}
      className="mt-3 min-w-0"
    >
      <p className="text-label text-ink-muted">
        {t("learningProfile.mastery.confirmed", {
          count: data.confirmed_concept_count,
        })}
      </p>
      <BaseChart
        option={option}
        ariaLabel={t("learningProfile.mastery.title")}
        className="bg-surface-strong mt-2 h-3 overflow-hidden rounded-sm"
      />
      <div className="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-4">
        {displayStatuses.map((status) => (
          <button
            type="button"
            key={status}
            aria-pressed={selected === status}
            className={cn(
              "text-label text-ink-muted hover:bg-surface-subtle focus-visible:ring-ring flex min-w-0 items-center justify-between gap-2 rounded-sm px-1 py-1 text-left focus-visible:ring-2",
              selected === status && "bg-surface-strong text-ink-strong",
            )}
            onClick={() => onSelect(selected === status ? undefined : status)}
          >
            <span className="text-label">
              {t(masteryStatusLabelKeys[status])}
            </span>
            <span className="text-label font-section tabular-nums">
              {data.status_counts[masteryStatusCountKeys[status]]}
            </span>
          </button>
        ))}
      </div>
      <p className="text-label text-ink-muted mt-3">
        {t("spaces.courseDetail.gps.coverage")}{" "}
        <span className="text-ink tabular-nums">
          {data.verified_concept_count} / {data.confirmed_concept_count}
        </span>
      </p>
      <div
        role="progressbar"
        aria-label={t("spaces.courseDetail.gps.coverage")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(data.coverage * 100)}
        className="bg-surface-strong mt-1.5 h-1.5 overflow-hidden rounded-full"
      >
        <div
          className="bg-ink-muted h-full rounded-full"
          style={{ width: `${data.coverage * 100}%` }}
        />
      </div>
    </section>
  );
}
