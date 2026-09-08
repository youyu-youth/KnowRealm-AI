import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { components } from "@knowrealm/api-types";
import { BaseChart } from "@/charts/BaseChart";
import { chartPalette, darkTooltipStyle, hexWithAlpha } from "@/charts/token";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";

type LlmUsageOut = components["schemas"]["LlmUsageOut"];

const compactNumber = new Intl.NumberFormat("zh-CN", { notation: "compact" });

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN");
}

// token 用量/天（全模型合计，model 明细由表格承载）；悬停附带当天调用次数。
function buildChartOption(daily: LlmUsageOut["daily"], t: TFunction) {
  const palette = chartPalette();
  return {
    grid: { left: 44, right: 4, top: 8, bottom: 20 },
    tooltip: {
      trigger: "axis",
      ...darkTooltipStyle(),
      formatter: (params: unknown) => {
        const first = (Array.isArray(params) ? params[0] : params) as
          { dataIndex: number } | undefined;
        const point = first ? daily[first.dataIndex] : undefined;
        if (!point) return "";
        return t("settings.providers.usage.chartTooltip", {
          date: point.date,
          tokens: formatNumber(point.total_tokens),
          calls: point.call_count,
        });
      },
    },
    xAxis: {
      type: "category",
      data: daily.map((point) => point.date),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: palette.border } },
      axisLabel: {
        color: palette.mutedForeground,
        interval: (index: number) => index % 5 === 0,
        formatter: (value: string) => value.slice(5).replace("-", "/"),
      },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: palette.mutedForeground,
        formatter: (value: number) => compactNumber.format(value),
      },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: [
      {
        type: "line",
        data: daily.map((point) => point.total_tokens),
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
                  { offset: 0, color: hexWithAlpha(palette.foreground, "18") },
                  { offset: 1, color: hexWithAlpha(palette.foreground, "03") },
                ],
              },
            }
          : undefined,
      },
    ],
  };
}

/** 服务与用量分区的用量卡：近 30 天调用量与 token 消耗（按模型汇总，不做计价）。 */
export function LlmUsageCard() {
  const { t } = useTranslation();
  const usage = useQuery({
    queryKey: settingsKeys.llmUsage,
    queryFn: settingsApi.getLlmUsage,
  });
  const chartOption = useMemo(
    () =>
      usage.data && usage.data.items.length > 0
        ? buildChartOption(usage.data.daily, t)
        : null,
    [usage.data, t],
  );

  if (usage.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("settings.providers.usage.loading")}
      </p>
    );
  }
  if (usage.isError) {
    return (
      <section>
        <h3 className="text-section font-section text-ink">
          {t("settings.providers.usage.title")}
        </h3>
        <p className="text-body text-muted-foreground mt-2">
          {usage.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => void usage.refetch()}
        >
          {t("settings.providers.retry")}
        </Button>
      </section>
    );
  }

  const { items } = usage.data;

  return (
    <section aria-labelledby="providers-usage-title">
      <h3
        id="providers-usage-title"
        className="text-section font-section text-ink"
      >
        {t("settings.providers.usage.title")}
      </h3>
      <p className="text-body text-muted-foreground mt-1">
        {t("settings.providers.usage.description")}
      </p>
      {items.length === 0 ? (
        <p className="text-body text-muted-foreground mt-4">
          {t("settings.providers.usage.empty")}
        </p>
      ) : (
        <>
          {chartOption ? (
            <BaseChart
              option={chartOption}
              ariaLabel={t("settings.providers.usage.chartLabel")}
              className="mt-5 h-40 w-full"
            />
          ) : null}
          <table className="text-body mt-5 w-full">
            <thead>
              <tr className="text-label text-muted-foreground border-border border-b">
                <th scope="col" className="py-2 pe-4 text-start">
                  {t("settings.providers.usage.model")}
                </th>
                <th scope="col" className="py-2 pe-4 text-end">
                  {t("settings.providers.usage.calls")}
                </th>
                <th scope="col" className="py-2 pe-4 text-end">
                  {t("settings.providers.usage.input")}
                </th>
                <th scope="col" className="py-2 pe-4 text-end">
                  {t("settings.providers.usage.output")}
                </th>
                <th scope="col" className="py-2 pe-4 text-end">
                  {t("settings.providers.usage.total")}
                </th>
                <th scope="col" className="py-2 text-end">
                  {t("settings.providers.usage.errors")}
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.model}
                  className="border-border border-b last:border-b-0"
                >
                  <td className="text-ink py-2.5 pe-4 font-medium break-all">
                    {item.model}
                  </td>
                  <td className="py-2.5 pe-4 text-end tabular-nums">
                    {formatNumber(item.call_count)}
                  </td>
                  <td className="py-2.5 pe-4 text-end tabular-nums">
                    {formatNumber(item.input_tokens)}
                  </td>
                  <td className="py-2.5 pe-4 text-end tabular-nums">
                    {formatNumber(item.output_tokens)}
                  </td>
                  <td className="text-ink-strong py-2.5 pe-4 text-end font-semibold tabular-nums">
                    {formatNumber(item.total_tokens)}
                  </td>
                  <td
                    className={`py-2.5 text-end tabular-nums ${item.error_count > 0 ? "text-danger" : "text-muted-foreground"}`}
                  >
                    {formatNumber(item.error_count)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
