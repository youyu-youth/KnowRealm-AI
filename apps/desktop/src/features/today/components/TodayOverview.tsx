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
import { Button } from "@/components/ui/button";

export function TodayOverview() {
  const { t, i18n } = useTranslation();
  const { view = "workbench", panel = "actions" } = useSearch({ from: "/" });
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
        panel: "actions",
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
            panel: "actions",
          }),
          replace: true,
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);
  useEffect(() => {
    if (panel === "review") {
      const preview = document.getElementById("today-summary-preview");
      preview?.focus({ preventScroll: true });
      preview?.scrollIntoView({ block: "nearest" });
    }
  }, [panel, selectedId]);
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
        className="today-workspace-tabs gap-3"
      >
        <header className="today-header flex flex-wrap items-center justify-between gap-3 px-2 py-2">
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
              className="data-active:bg-primary data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground gap-3 px-5 py-2"
            >
              {t("today.workspace.workbench")}
              <kbd className="text-label font-sans opacity-80">Ctrl 1</kbd>
            </TabsTrigger>
            <TabsTrigger
              value="orbit"
              aria-keyshortcuts="Control+2"
              className="data-active:bg-primary data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground gap-3 px-5 py-2"
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
          className="today-pane-switcher gap-2 px-2"
          role="group"
          aria-label={t("today.workspace.panelSwitch")}
        >
          {(["actions", "pending", "review"] as const).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={panel === value ? "secondary" : "ghost"}
              aria-pressed={panel === value}
              aria-controls={`today-pane-${value}`}
              onClick={() =>
                void navigate({
                  search: (previous) => ({ ...previous, panel: value }),
                  replace: true,
                })
              }
            >
              {t(
                value === "review"
                  ? "today.workspace.focusAndSummary"
                  : value === "pending"
                    ? "today.workspace.pending"
                    : view === "orbit"
                      ? "today.stats.title"
                      : "today.workspace.actions",
              )}
            </Button>
          ))}
        </div>
        <div
          className="today-grid"
          data-panel={panel}
          tabIndex={0}
          role="region"
          aria-label={t("today.workspace.workArea")}
        >
          <aside
            id="today-pane-pending"
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
              onSelect={(id) => {
                setSelectedId(id);
                void navigate({
                  search: (previous) => ({ ...previous, panel: "review" }),
                  replace: true,
                });
              }}
            />
            <div
              className="today-assets-list"
              role="region"
              aria-label={t("today.overview.assetsTitle")}
              tabIndex={0}
            >
              <TodayAssets />
            </div>
          </aside>
          <div id="today-pane-actions" className="today-center min-w-0">
            <TabsContent
              value="workbench"
              className="today-center-content today-workbench m-0 flex flex-col gap-3"
              tabIndex={0}
            >
              <TodayActions
                summaries={pending.data}
                loading={pending.isPending}
                error={pending.isError}
                onRetry={() => void pending.refetch()}
              />
              <div className="today-secondary">
                <TodayStatsBand compact />
                <TodayQuickStart />
              </div>
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
            id="today-pane-review"
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
