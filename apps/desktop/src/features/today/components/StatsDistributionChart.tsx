import { useAppearanceSnapshot } from "@/hooks/useAppearanceSnapshot";
import { useTranslation } from "react-i18next";

import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle } from "@/charts/token";
import {
  distributionSlices,
  distributionTotalHours,
} from "@/features/today/mockInsights";

function buildDistributionOption(t: (key: string) => string) {
  const palette = chartPalette();
  const colors = [
    palette.primary,
    palette.foreground,
    palette.neutralForeground,
    palette.mutedForeground,
    palette.faintForeground,
    palette.borderStrong,
  ];

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
  useAppearanceSnapshot();
  const option = buildDistributionOption(t);
  const palette = chartPalette();
  const colors = [
    palette.primary,
    palette.foreground,
    palette.neutralForeground,
    palette.mutedForeground,
    palette.faintForeground,
    palette.borderStrong,
  ];

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
        className="flex max-w-64 min-w-0 flex-1 flex-col gap-1.5"
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
