import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { BaseChart } from "@/charts/BaseChart";
import type { TodayTrendPoint } from "@/features/today/api/today";
import { formatLearningDurationText } from "@/features/today/duration";

const MS_PER_HOUR = 3_600_000;

// 图表配色读语义 token 的计算值，亮暗主题（.dark 类）随之生效。
// 主题切换只发生在设置页，返回今日页即重挂载并重读 token，故无需监听类翻转；
// 取不到值（如 jsdom 无样式表）时交由 echarts 默认色兜底，不阻塞渲染。
function cssVar(name: string): string | undefined {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value === "" ? undefined : value;
}

function hexWithAlpha(color: string | undefined, alpha: string) {
  if (!color) return undefined;
  return /^#[0-9a-f]{6}$/i.test(color) ? `${color}${alpha}` : color;
}

function buildTrendOption(points: TodayTrendPoint[], t: TFunction) {
  const foreground = cssVar("--foreground");
  const primary = cssVar("--primary");
  const mutedForeground = cssVar("--muted-foreground");
  const border = cssVar("--border");
  const axisLabelColor = { color: mutedForeground };

  return {
    // echarts 6 起坐标标签防溢出为默认行为（containLabel 已废弃）。
    grid: { left: 8, right: 8, top: 28, bottom: 0 },
    tooltip: {
      trigger: "axis",
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
        ...axisLabelColor,
        formatter: (value: string) => value.slice(5).replace("-", "/"),
      },
    },
    yAxis: {
      type: "value",
      name: t("today.stats.trendUnit"),
      nameTextStyle: { color: mutedForeground },
      axisLabel: axisLabelColor,
      splitLine: { lineStyle: { color: border } },
    },
    series: [
      {
        type: "line",
        name: t("today.stats.title"),
        // y 轴以小时计；smooth 关闭，无学习的日子如实平线。
        data: points.map((point) =>
          Number((point.total_ms / MS_PER_HOUR).toFixed(2)),
        ),
        smooth: false,
        showSymbol: false,
        lineStyle: { width: 2, color: foreground },
        areaStyle: primary
          ? {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: hexWithAlpha(primary, "33") },
                  { offset: 1, color: hexWithAlpha(primary, "05") },
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
  ariaLabel: string;
  className?: string;
};

export function StatsTrendChart({
  points,
  ariaLabel,
  className,
}: StatsTrendChartProps) {
  const { t } = useTranslation();
  const option = useMemo(() => buildTrendOption(points, t), [points, t]);
  return (
    <BaseChart option={option} ariaLabel={ariaLabel} className={className} />
  );
}
