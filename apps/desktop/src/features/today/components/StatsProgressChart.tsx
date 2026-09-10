import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle, hexWithAlpha } from "@/charts/token";
import {
  lastNDates,
  progressDayCount,
  progressSeries,
} from "@/features/today/mockInsights";

// 三层堆叠面积使用主题灰阶与不同透明度，手写图例复用同一色值。
function progressLayerColors() {
  const palette = chartPalette();
  return [palette.primary, palette.foreground, palette.mutedForeground];
}

function buildProgressOption(t: (key: string) => string) {
  const palette = chartPalette();
  const lineColors = progressLayerColors();
  const areaTops = ["4D", "33", "26"];
  const areaBottoms = ["0D", "08", "05"];

  return {
    grid: { left: 8, right: 8, top: 12, bottom: 0 },
    tooltip: {
      trigger: "axis",
      ...darkTooltipStyle(),
    },
    xAxis: {
      type: "category",
      data: lastNDates(progressDayCount),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: palette.border } },
      axisLabel: {
        color: palette.mutedForeground,
        formatter: (value: string) => value.slice(5).replace("-", "/"),
      },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: palette.mutedForeground },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: progressSeries.map((series, index) => ({
      type: "line",
      name: t(series.nameKey),
      stack: "progress",
      data: series.values,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 1.5, color: lineColors[index] },
      areaStyle: {
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            {
              offset: 0,
              color: hexWithAlpha(lineColors[index], areaTops[index]),
            },
            {
              offset: 1,
              color: hexWithAlpha(lineColors[index], areaBottoms[index]),
            },
          ],
        },
      },
    })),
  };
}

type StatsProgressChartProps = {
  ariaLabel: string;
  className?: string;
};

export function StatsProgressChart({
  ariaLabel,
  className,
}: StatsProgressChartProps) {
  const { t } = useTranslation();
  const option = useMemo(() => buildProgressOption(t), [t]);
  const lineColors = progressLayerColors();

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ul
        aria-label={t("today.stats.insights.legendLabel")}
        className="flex flex-wrap items-center gap-x-4 gap-y-1"
      >
        {progressSeries.map((series, index) => (
          <li
            key={series.nameKey}
            className="text-label text-muted-foreground flex items-center gap-1.5"
          >
            <span
              aria-hidden="true"
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: lineColors[index] }}
            />
            {t(series.nameKey)}
          </li>
        ))}
      </ul>
      <BaseChart
        option={option}
        ariaLabel={ariaLabel}
        className={className ?? "h-36 w-full"}
      />
    </div>
  );
}
