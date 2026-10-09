import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { HardDrive } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { todayKeys } from "@/features/today/api/keys";
import { todayApi } from "@/features/today/api/today";
import { TodayActions } from "@/features/today/components/TodayActions";
import { TodayAssets } from "@/features/today/components/TodayAssets";
import { TodayFocus } from "@/features/today/components/TodayFocus";
import { TodayPending } from "@/features/today/components/TodayPending";
import { TodayQuickStart } from "@/features/today/components/TodayQuickStart";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";
import { TodaySummaryPreview } from "@/features/today/components/TodaySummaryPreview";
import "@/features/today/components/TodayWorkspace.css";

export function TodayOverview() {
  const { t, i18n } = useTranslation();
  const { view = "workbench" } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const [selectedId, setSelectedId] = useState<string>();
  const [now, setNow] = useState(() => new Date());
  const pending = useQuery({
    queryKey: todayKeys.pendingSummaries,
    queryFn: todayApi.pendingSummaries,
  });
  const plans = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
  });
  const selected =
    pending.data?.find((record) => record.record_id === selectedId) ??
    pending.data?.[0];
  const setView = (next: string) =>
    void navigate({
      search: (previous) => ({
        ...previous,
        view: next === "orbit" ? "orbit" : "workbench",
      }),
      replace: true,
    });

  useEffect(() => {
    const tick = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(tick);
  }, []);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest(
          "input, textarea, select, [contenteditable=true], [role=dialog]",
        )
      )
        return;
      if (!event.ctrlKey || event.altKey || event.shiftKey || event.metaKey)
        return;
      if (event.key === "1" || event.key === "2") {
        event.preventDefault();
        void navigate({
          search: (previous) => ({
            ...previous,
            view: event.key === "2" ? "orbit" : "workbench",
          }),
          replace: true,
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);
  const date = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(now);

  return (
    <div className="today-workspace">
      <Tabs
        value={view}
        onValueChange={(value) => setView(String(value))}
        className="gap-2"
      >
        <header className="flex flex-wrap items-center justify-between gap-3 px-2 py-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-headline font-headline">{t("today.title")}</h1>
            <p className="text-body text-ink-muted border-border-subtle border-l pl-3">
              {date}
            </p>
          </div>
          <TabsList className="h-auto max-w-full p-1">
            <TabsTrigger
              value="workbench"
              aria-keyshortcuts="Control+1"
              className="data-active:bg-today-accent data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground gap-3 px-5 py-2"
            >
              {t("today.workspace.workbench")}
              <kbd className="text-label font-sans opacity-80">Ctrl 1</kbd>
            </TabsTrigger>
            <TabsTrigger
              value="orbit"
              aria-keyshortcuts="Control+2"
              className="data-active:bg-today-accent data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground gap-3 px-5 py-2"
            >
              {t("today.workspace.orbit")}
              <kbd className="text-label font-sans opacity-80">Ctrl 2</kbd>
            </TabsTrigger>
          </TabsList>
          <p className="text-label text-ink-muted flex items-center gap-2">
            <HardDrive className="size-4" aria-hidden="true" />
            {t("today.workspace.local")}
          </p>
        </header>
        <div
          className="today-grid"
          tabIndex={0}
          role="region"
          aria-label={t("today.workspace.workArea")}
        >
          <aside
            aria-label={t("today.workspace.pending")}
            className="today-panel today-left"
            tabIndex={0}
          >
            <TodayPending
              summaries={pending.data ?? []}
              pending={pending.isPending}
              error={pending.isError}
              onRetry={() => void pending.refetch()}
              selectedId={selected?.record_id}
              onSelect={setSelectedId}
            />
            <TodayAssets />
          </aside>
          <div className="today-center min-w-0">
            <TabsContent
              value="workbench"
              className="today-center-content m-0 flex flex-col gap-2"
              tabIndex={0}
            >
              <TodayStatsBand compact />
              <TodayActions
                summaries={pending.data}
                loading={pending.isPending}
                error={pending.isError}
                onRetry={() => void pending.refetch()}
              />
              <TodayQuickStart />
            </TabsContent>
            <TabsContent
              value="orbit"
              className="today-center-content m-0"
              tabIndex={0}
            >
              <TodayStatsBand />
              <div className="mt-3">
                <TodayQuickStart />
              </div>
            </TabsContent>
          </div>
          <aside
            aria-label={t("today.rightRail.label")}
            className="today-rail min-w-0 gap-2"
            tabIndex={0}
          >
            <TodayFocus task={plans.data?.[0]} />
            <TodaySummaryPreview
              key={selected?.record_id ?? "sample"}
              record={selected}
              loading={pending.isPending}
              error={pending.isError}
            />
          </aside>
        </div>
      </Tabs>
    </div>
  );
}
