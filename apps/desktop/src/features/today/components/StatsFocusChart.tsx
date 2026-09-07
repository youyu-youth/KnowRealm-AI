import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle, hexWithAlpha } from "@/charts/token";
import {
  focusByHourMinutes,
  focusHourLabels,
} from "@/features/today/mockInsights";

function buildFocusOption(t: TFunction) {
  const palette = chartPalette();

  return {
    grid: { left: 8, right: 8, top: 12, bottom: 0 },
    tooltip: {
      trigger: "axis",
      ...darkTooltipStyle(),
      valueFormatter: (value: unknown) =>
        `${(Number(value) / 60).toFixed(1)} ${t("today.stats.insights.unitH")}`,
    },
    xAxis: {
      type: "category",
      data: focusHourLabels(),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: palette.border } },
      axisLabel: {
        color: palette.mutedForeground,
        interval: (index: number) => index % 6 === 0,
      },
    },
    // 示意形态图：y 轴不显示刻度，专注强度由面积轮廓与 tooltip 表达。
    yAxis: { type: "value", show: false, min: 0 },
    series: [
      {
        type: "line",
        data: focusByHourMinutes,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: palette.foreground },
        areaStyle: palette.foreground
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: hexWithAlpha(palette.foreground, "2E") },
                  { offset: 1, color: hexWithAlpha(palette.foreground, "05") },
                ],
              },
            }
          : undefined,
      },
    ],
  };
}

type StatsFocusChartProps = {
  ariaLabel: string;
  className?: string;
};

export function StatsFocusChart({
  ariaLabel,
  className,
}: StatsFocusChartProps) {
  const { t } = useTranslation();
  const option = useMemo(() => buildFocusOption(t), [t]);
  return (
    <BaseChart option={option} ariaLabel={ariaLabel} className={className} />
  );
}
