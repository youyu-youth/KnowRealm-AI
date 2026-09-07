import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle, hexWithAlpha } from "@/charts/token";
import type { TodayTrendPoint } from "@/features/today/api/today";
import { formatLearningDurationText } from "@/features/today/duration";

const MS_PER_HOUR = 3_600_000;

function buildTrendOption(
  points: TodayTrendPoint[],
  showSymbol: boolean,
  t: TFunction,
) {
  const palette = chartPalette();

  return {
    grid: { left: 8, right: 8, top: 28, bottom: 0 },
    tooltip: {
      trigger: "axis",
      ...darkTooltipStyle(),
      valueFormatter: (value: unknown) =>
        formatLearningDurationText(Number(value) * MS_PER_HOUR, t),
    },
    xAxis: {
      type: "category",
      data: points.map((point) => point.date),
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
      name: t("today.stats.trendUnit"),
      nameTextStyle: { color: palette.mutedForeground },
      axisLabel: { color: palette.mutedForeground },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: [
      {
        type: "line",
        name: t("today.stats.title"),
        // y 轴以小时计；7 天档显示空心圆点，30 天档点距过密仅保留 tooltip。
        data: points.map((point) =>
          Number((point.total_ms / MS_PER_HOUR).toFixed(2)),
        ),
        smooth: false,
        showSymbol,
        symbol: "circle",
        symbolSize: 7,
        itemStyle: {
          color: palette.card,
          borderColor: palette.foreground,
          borderWidth: 2,
        },
        lineStyle: { width: 2, color: palette.foreground },
        areaStyle: palette.primary
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: hexWithAlpha(palette.primary, "24") },
                  { offset: 1, color: hexWithAlpha(palette.primary, "05") },
                ],
              },
            }
          : undefined,
      },
    ],
  };
}

type StatsTrendChartProps = {
  points: TodayTrendPoint[];
  showSymbol: boolean;
  ariaLabel: string;
  className?: string;
};

export function StatsTrendChart({
  points,
  showSymbol,
  ariaLabel,
  className,
}: StatsTrendChartProps) {
  const { t } = useTranslation();
  const option = useMemo(
    () => buildTrendOption(points, showSymbol, t),
    [points, showSymbol, t],
  );
  return (
    <BaseChart option={option} ariaLabel={ariaLabel} className={className} />
  );
}
