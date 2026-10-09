import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  todayApi,
  type TodayTrendPoint,
  type TrendDays,
} from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { StatsFocusChart } from "@/features/today/components/StatsFocusChart";
import { StatsDistributionChart } from "@/features/today/components/StatsDistributionChart";
import { StatsInsightCard } from "@/features/today/components/StatsInsightCard";
import { StatsMetrics } from "@/features/today/components/StatsMetrics";
import { StatsProgressChart } from "@/features/today/components/StatsProgressChart";
import { StatsRadarChart } from "@/features/today/components/StatsRadarChart";
import { StatsTrendChart } from "@/features/today/components/StatsTrendChart";

const MS_PER_HOUR = 3_600_000;

function sumMs(points: TodayTrendPoint[]): number {
  return points.reduce((total, point) => total + point.total_ms, 0);
}

// 大数字照参考稿用一位小数小时（28.6 h）；六格指标带维持两档中文格式。
function formatHoursBig(ms: number): string {
  return (ms / MS_PER_HOUR).toFixed(1);
}

export function TodayStatsBand({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const [days, setDays] = useState<TrendDays>(7);
  const [themeRevision, setThemeRevision] = useState(0);

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setThemeRevision((revision) => revision + 1),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "style"],
    });
    queueMicrotask(() => setThemeRevision((revision) => revision + 1));
    return () => observer.disconnect();
  }, []);

  const stats = useQuery({
    queryKey: todayKeys.stats,
    queryFn: todayApi.stats,
  });
  // 趋势固定取 30 天序列：7 天档 = 尾部切片，30 天档 = 全量；切档纯前端切片零请求，
  // 「较上周」由同序列前后两段计算（对比仅 7 天档有意义）。
  const trend = useQuery({
    queryKey: todayKeys.trend(30),
    queryFn: () => todayApi.trend(30),
    placeholderData: keepPreviousData,
  });

  const points = trend.data ?? [];
  const windowPoints = days === 7 ? points.slice(-7) : points;
  const windowTotalMs = sumMs(windowPoints);
  const comparison = buildWeekComparison(points, days);

  if (themeRevision === 0) return null;

  return (
    <section key={themeRevision} className="min-w-0">
      <div
        aria-label={t("today.stats.title")}
        role="region"
        className="today-panel today-stats p-4"
      >
        <StatsBandHeader
          days={days}
          onDaysChange={setDays}
          total={
            compact &&
            !stats.isPending &&
            !trend.isPending &&
            !stats.isError &&
            !trend.isError
              ? formatHoursBig(windowTotalMs)
              : undefined
          }
        />
        {stats.isPending || trend.isPending ? (
          <p
            role="status"
            className="text-body text-muted-foreground mt-6 flex items-center gap-2"
          >
            <Spinner aria-hidden="true" />
            {t("today.stats.loading")}
          </p>
        ) : stats.isError || trend.isError ? (
          <div role="alert" className="border-border mt-6 border-t pt-6">
            <h3 className="text-section font-section text-ink">
              {t("today.stats.errorTitle")}
            </h3>
            <p className="text-body text-muted-foreground mt-2">
              {t("today.stats.errorDescription")}
            </p>
            <Button
              variant="outline"
              className="mt-5"
              onClick={() => {
                void stats.refetch();
                void trend.refetch();
              }}
            >
              {t("today.stats.retry")}
            </Button>
          </div>
        ) : (
          <>
            <div
              className={cn(
                "mt-3 flex min-w-0 gap-3",
                compact
                  ? "flex-col"
                  : "compact:flex-row compact:items-end compact:gap-8 flex-col",
              )}
            >
              {!compact ? (
                <div className="compact:w-32 compact:pb-5 shrink-0">
                  <p
                    className={cn(
                      "font-headline text-ink-strong tabular-nums",
                      compact ? "text-body" : "text-stat",
                    )}
                  >
                    {formatHoursBig(windowTotalMs)}
                    <span className="text-label font-label text-muted-foreground">
                      {" "}
                      {t("today.stats.insights.unitH")}
                    </span>
                  </p>
                  {comparison ? (
                    <p className="text-label text-muted-foreground mt-1">
                      {t("today.stats.weekOverWeek")}{" "}
                      <span className="text-ink font-medium">{comparison}</span>
                    </p>
                  ) : null}
                </div>
              ) : comparison ? (
                <p className="text-label text-ink-muted">
                  {t("today.stats.weekOverWeek")} {comparison}
                </p>
              ) : null}
              <StatsTrendChart
                points={windowPoints}
                showSymbol={days === 7}
                ariaLabel={t("today.stats.trendChartLabel")}
                className={cn(
                  "min-w-0",
                  compact ? "h-40 w-full" : "h-44 flex-1",
                )}
              />
            </div>
            <Collapsible
              defaultOpen={!compact}
              className="border-border mt-3 border-t pt-2"
            >
              <CollapsibleTrigger className="text-label text-ink-muted flex w-full items-center justify-between gap-2 py-1">
                {t("today.workspace.metrics")}
                <ChevronDown className="size-3.5" aria-hidden="true" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <StatsMetrics stats={stats.data} />
              </CollapsibleContent>
            </Collapsible>
          </>
        )}
      </div>

      {/* 洞察小图卡为示意数据，不依赖统计查询，加载/失败不影响渲染。 */}
      {!compact ? (
        <div className="compact:grid-cols-2 mt-4 grid grid-cols-1 gap-3">
          <StatsInsightCard title={t("today.stats.insights.radarTitle")}>
            <StatsRadarChart
              ariaLabel={t("today.stats.insights.radarChartLabel")}
              className="h-40 w-full"
            />
          </StatsInsightCard>
          <StatsInsightCard title={t("today.stats.insights.distributionTitle")}>
            <StatsDistributionChart
              ariaLabel={t("today.stats.insights.distributionChartLabel")}
            />
          </StatsInsightCard>
          <StatsInsightCard title={t("today.stats.insights.focusTitle")}>
            <StatsFocusChart
              ariaLabel={t("today.stats.insights.focusChartLabel")}
              className="h-28 w-full"
            />
          </StatsInsightCard>
          <StatsInsightCard title={t("today.stats.insights.progressTitle")}>
            <StatsProgressChart
              ariaLabel={t("today.stats.insights.progressChartLabel")}
              className="h-28 w-full"
            />
          </StatsInsightCard>
        </div>
      ) : null}
    </section>
  );
}

// 近 7 天 vs 前 7 天（同一 30 天序列切片）：仅 7 天档提供对比；
// 前一周期全 0 时显示绝对增量，两段皆 0 则不显示。
function buildWeekComparison(
  points: TodayTrendPoint[],
  days: TrendDays,
): string | null {
  if (days !== 7 || points.length < 14) return null;
  const currentMs = sumMs(points.slice(-7));
  const previousMs = sumMs(points.slice(-14, -7));
  if (currentMs === 0 && previousMs === 0) return null;
  if (previousMs === 0) return `+${formatHoursBig(currentMs)}`;
  const percent = Math.round(((currentMs - previousMs) / previousMs) * 100);
  if (percent === 0) return "–";
  const arrow = percent > 0 ? "↑" : "↓";
  return `${arrow} ${Math.abs(percent)}%`;
}

type StatsBandHeaderProps = {
  days: TrendDays;
  onDaysChange: (days: TrendDays) => void;
  total?: string;
};

function StatsBandHeader({ days, onDaysChange, total }: StatsBandHeaderProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="today-stats-title" className="today-heading">
          {t("today.stats.title")}
        </h2>
        {total !== undefined ? (
          <p className="text-body font-medium tabular-nums">
            {total}{" "}
            <span className="text-label text-ink-muted">
              {t("today.stats.insights.unitH")}
            </span>
          </p>
        ) : null}
      </div>
      <Tabs
        value={String(days)}
        onValueChange={(value) => onDaysChange(value === "30" ? 30 : 7)}
      >
        <TabsList>
          <TabsTrigger
            value="7"
            className="data-active:bg-primary data-active:text-primary-foreground"
          >
            {t("today.stats.last7Days")}
          </TabsTrigger>
          <TabsTrigger
            value="30"
            className="data-active:bg-primary data-active:text-primary-foreground"
          >
            {t("today.stats.last30Days")}
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </div>
  );
}
