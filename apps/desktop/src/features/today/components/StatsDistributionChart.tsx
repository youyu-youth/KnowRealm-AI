import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle, hexWithAlpha } from "@/charts/token";
import {
  distributionSlices,
  distributionTotalHours,
} from "@/features/today/mockInsights";

// 单色层次（learning 蓝 → 灰）对应分类占比从大到小，与右侧图例共用色值。
function sliceColors() {
  const palette = chartPalette();
  return [
    palette.learning,
    hexWithAlpha(palette.learning, "B3"),
    hexWithAlpha(palette.learning, "73"),
    hexWithAlpha(palette.learning, "40"),
    hexWithAlpha(palette.mutedForeground, "80"),
    hexWithAlpha(palette.mutedForeground, "4D"),
  ];
}

function buildDistributionOption(t: (key: string) => string) {
  const palette = chartPalette();
  const colors = sliceColors();

  return {
    tooltip: {
      trigger: "item",
      ...darkTooltipStyle(),
      formatter: (params: { name: string; value: number }) =>
        `${params.name} ${params.value}%`,
    },
    series: [
      {
        type: "pie",
        radius: ["64%", "88%"],
        center: ["50%", "50%"],
        label: { show: false },
        labelLine: { show: false },
        // 静态色面：hover 不缩放不位移，仅出 tooltip（DESIGN 禁悬浮动画）。
        emphasis: { scale: false },
        itemStyle: { borderColor: palette.card, borderWidth: 2 },
        data: distributionSlices.map((slice, index) => ({
          name: t(slice.nameKey),
          value: slice.percent,
          itemStyle: { color: colors[index] },
        })),
      },
    ],
  };
}

type StatsDistributionChartProps = {
  ariaLabel: string;
};

export function StatsDistributionChart({
  ariaLabel,
}: StatsDistributionChartProps) {
  const { t } = useTranslation();
  const option = useMemo(() => buildDistributionOption(t), [t]);
  const colors = sliceColors();

  return (
    <div className="flex min-w-0 items-center gap-4">
      <div className="relative size-36 shrink-0">
        <BaseChart
          option={option}
          ariaLabel={ariaLabel}
          className="size-full"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
        >
          <p className="text-headline font-headline text-ink-strong tabular-nums">
            {distributionTotalHours}
            <span className="text-label font-label text-muted-foreground">
              {" "}
              {t("today.stats.insights.unitH")}
            </span>
          </p>
          <p className="text-label text-muted-foreground mt-0.5">
            {t("today.stats.insights.distributionTotal")}
          </p>
        </div>
      </div>
      <ul
        aria-label={t("today.stats.insights.legendLabel")}
        className="flex min-w-0 flex-1 flex-col gap-1.5"
      >
        {distributionSlices.map((slice, index) => (
          <li
            key={slice.nameKey}
            className="text-label text-muted-foreground flex min-w-0 items-center gap-1.5"
          >
            <span
              aria-hidden="true"
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: colors[index] }}
            />
            <span className="min-w-0 truncate">{t(slice.nameKey)}</span>
            <span className="ml-auto tabular-nums">{slice.percent}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
