import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { todayApi, type TrendDays } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { StatsMetrics } from "@/features/today/components/StatsMetrics";
import { StatsTrendChart } from "@/features/today/components/StatsTrendChart";

export function TodayStatsBand() {
  const { t } = useTranslation();
  const [days, setDays] = useState<TrendDays>(7);
  const stats = useQuery({
    queryKey: todayKeys.stats,
    queryFn: todayApi.stats,
  });
  const trend = useQuery({
    queryKey: todayKeys.trend(days),
    queryFn: () => todayApi.trend(days),
    // 切换即重取（工单契约）：不沿用全局 staleTime，回切缓存档位也发新请求。
    staleTime: 0,
    // 切换时保留旧曲线直到新序列到达，避免整带闪回加载态。
    placeholderData: keepPreviousData,
  });

  return (
    <section className="border-border mt-8 border-t pt-8">
      <StatsBandHeader days={days} onDaysChange={setDays} />
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
          <StatsTrendChart
            points={trend.data ?? []}
            ariaLabel={t("today.stats.trendChartLabel")}
            className="mt-4 h-64 w-full"
          />
          <StatsMetrics stats={stats.data} />
        </>
      )}
    </section>
  );
}

type StatsBandHeaderProps = {
  days: TrendDays;
  onDaysChange: (days: TrendDays) => void;
};

function StatsBandHeader({ days, onDaysChange }: StatsBandHeaderProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <h2 className="text-section font-section text-ink">
        {t("today.stats.title")}
      </h2>
      <Tabs
        value={String(days)}
        onValueChange={(value) => onDaysChange(value === "30" ? 30 : 7)}
      >
        <TabsList>
          <TabsTrigger value="7">{t("today.stats.last7Days")}</TabsTrigger>
          <TabsTrigger value="30">{t("today.stats.last30Days")}</TabsTrigger>
        </TabsList>
      </Tabs>
    </div>
  );
}
