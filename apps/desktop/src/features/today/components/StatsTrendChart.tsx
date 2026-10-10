import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, cssVar, darkTooltipStyle } from "@/charts/token";
import type { TodayTrendPoint } from "@/features/today/api/today";
import { formatLearningDurationText } from "@/features/today/duration";

const MS_PER_HOUR = 3_600_000;

function buildTrendOption(
  points: TodayTrendPoint[],
  showSymbol: boolean,
  t: TFunction,
) {
  const palette = chartPalette();
  const accent = cssVar("--today-accent");
  const muted = cssVar("--today-muted");
  const border = cssVar("--today-border");
  const fontSize =
    parseFloat(getComputedStyle(document.documentElement).fontSize) * 0.75 ||
    12;

  return {
    animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    textStyle: { fontSize },
    grid: { left: 32, right: 16, top: 24, bottom: 24 },
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
      axisLine: { lineStyle: { color: border } },
      axisLabel: {
        hideOverlap: true,
        color: muted,
        fontSize,
        formatter: (value: string) => value.slice(5).replace("-", "/"),
      },
    },
    yAxis: {
      type: "value",
      name: t("today.stats.trendUnit"),
      nameTextStyle: { color: muted, fontSize },
      splitNumber: 3,
      axisLabel: { color: muted, fontSize, hideOverlap: true },
      splitLine: { lineStyle: { color: border, type: "dashed" } },
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
        symbolSize: 6,
        itemStyle: {
          color: palette.card,
          borderColor: accent,
          borderWidth: 1.5,
        },
        lineStyle: { width: 1.5, color: accent },
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
