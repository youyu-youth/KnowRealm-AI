import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle } from "@/charts/token";
import {
  radarIndicators,
  radarLastWeek,
  radarThisWeek,
} from "@/features/today/mockInsights";

function buildRadarOption(t: (key: string) => string) {
  const palette = chartPalette();

  return {
    tooltip: { trigger: "item", ...darkTooltipStyle() },
    radar: {
      indicator: radarIndicators.map((indicator) => ({
        name: t(indicator.nameKey),
        max: indicator.max,
      })),
      radius: "68%",
      center: ["50%", "52%"],
      axisName: { color: palette.mutedForeground },
      axisLine: { lineStyle: { color: palette.border } },
      splitLine: { lineStyle: { color: palette.border } },
      splitArea: { show: false },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            name: t("today.stats.insights.thisWeek"),
            value: radarThisWeek,
            lineStyle: { width: 2, color: palette.foreground },
            itemStyle: { color: palette.foreground },
            areaStyle: palette.foreground
              ? { color: palette.foreground, opacity: 0.14 }
              : undefined,
            symbolSize: 4,
          },
          {
            name: t("today.stats.insights.lastWeek"),
            value: radarLastWeek,
            lineStyle: {
              width: 1.5,
              color: palette.mutedForeground,
              type: "dashed",
            },
            itemStyle: { color: palette.mutedForeground },
            symbolSize: 3,
          },
        ],
      },
    ],
  };
}

type StatsRadarChartProps = {
  ariaLabel: string;
  className?: string;
};

export function StatsRadarChart({
  ariaLabel,
  className,
}: StatsRadarChartProps) {
  const { t } = useTranslation();
  const option = useMemo(() => buildRadarOption(t), [t]);
  const palette = chartPalette();

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ul
        aria-label={t("today.stats.insights.legendLabel")}
        className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1"
      >
        <li className="text-label text-muted-foreground flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: palette.foreground }}
          />
          {t("today.stats.insights.thisWeek")}
        </li>
        <li className="text-label text-muted-foreground flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: palette.mutedForeground }}
          />
          {t("today.stats.insights.lastWeek")}
        </li>
      </ul>
      <BaseChart
        option={option}
        ariaLabel={ariaLabel}
        className={className ?? "h-40 w-full"}
      />
    </div>
  );
}
