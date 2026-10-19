import { useTranslation } from "react-i18next";
import { enUS, zhCN } from "react-day-picker/locale";
import { BaseChart } from "@/charts/BaseChart";
import { rootFontSize } from "@/charts/dom";
import { cssVar, darkTooltipStyle } from "@/charts/token";
import type { TodayTrendPoint } from "@/features/today/api/today";
import { useAppearanceSnapshot } from "@/hooks/useAppearanceSnapshot";

export function ProfileActivityHeatmap({
  points,
  selected,
  onSelect,
}: {
  points: TodayTrendPoint[];
  selected: string;
  onSelect: (date: string) => void;
}) {
  const { t, i18n } = useTranslation();
  useAppearanceSnapshot();
  const ordered = [...points].sort((first, second) =>
    first.date.localeCompare(second.date),
  );
  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  if (!first || !last) {
    return (
      <p className="text-label text-ink-muted mt-4">
        {t("learningProfile.calendar.noData")}
      </p>
    );
  }
  const locale = i18n.resolvedLanguage?.startsWith("zh") ? zhCN : enUS;
  const colors = [
    cssVar("--surface-strong"),
    cssVar("--ink-faint"),
    cssVar("--ink-muted"),
    cssVar("--ink-strong"),
  ];
  return (
    <div className="mt-4 max-w-64">
      <div
        className="text-label text-ink-muted mb-2 grid grid-cols-7 text-center"
        aria-hidden="true"
      >
        {([1, 2, 3, 4, 5, 6, 0] as const).map((weekday) => (
          <span key={weekday}>
            {locale.localize.day(weekday, { width: "narrow" })}
          </span>
        ))}
      </div>
      <BaseChart
        className="h-profile-heatmap w-full"
        ariaLabel={t("learningProfile.calendar.heatmapDescription")}
        option={{
          animation: false,
          tooltip: {
            ...darkTooltipStyle(),
            confine: true,
            renderMode: "richText",
            formatter: "{b}",
            textStyle: {
              color: cssVar("--paper"),
              fontFamily: cssVar("--font-sans"),
              fontSize: rootFontSize() * 0.75,
            },
          },
          calendar: {
            range: [first.date, last.date],
            orient: "vertical",
            left: 0,
            right: 0,
            top: 0,
            bottom: 0,
            cellSize: "auto",
            dayLabel: { show: false, firstDay: 1 },
            monthLabel: { show: false },
            yearLabel: { show: false },
            splitLine: { show: false },
            itemStyle: { color: "transparent", borderWidth: 0 },
          },
          visualMap: {
            show: false,
            type: "piecewise",
            dimension: 1,
            pieces: [
              { value: 0, color: colors[0] },
              { gt: 0, lt: 1800000, color: colors[1] },
              { gte: 1800000, lt: 3600000, color: colors[2] },
              { gte: 3600000, color: colors[3] },
            ],
          },
          series: [
            {
              type: "heatmap",
              coordinateSystem: "calendar",
              data: ordered.map((point) => ({
                name: `${point.date}\n${t("learningProfile.calendar.minutes", {
                  count: Math.round(point.total_ms / 60000),
                })}`,
                value: [point.date, point.total_ms],
                itemStyle: {
                  borderColor: cssVar(
                    point.date === selected ? "--ring" : "--paper",
                  ),
                  borderWidth: 2,
                },
              })),
              emphasis: {
                itemStyle: { borderColor: cssVar("--ring"), borderWidth: 2 },
              },
            },
          ],
        }}
        onItemSelect={(event) => {
          if (event.componentType !== "series") return;
          const point = ordered[event.dataIndex];
          if (point) onSelect(point.date);
        }}
      />
      <p className="text-label text-ink-muted mt-2 flex items-center justify-end gap-1.5">
        {t("learningProfile.calendar.less")}
        {colors.map((color, index) => (
          <span
            key={index}
            className="size-2.5 rounded-xs"
            style={{ backgroundColor: color }}
            aria-hidden="true"
          />
        ))}
        {t("learningProfile.calendar.more")}
      </p>
      <p className="text-label text-ink-muted mt-2">
        {t("learningProfile.calendar.heatmapHint")}
      </p>
    </div>
  );
}
