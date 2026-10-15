import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { HardDrive, PanelRightClose, Timer } from "lucide-react";
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
import { useTodayRefresh } from "@/features/today/useTodayRefresh";
import "@/features/today/components/TodayWorkspace.css";
import { Button } from "@/components/ui/button";

export function TodayOverview() {
  const { t, i18n } = useTranslation();
  const {
    view = "workbench",
    panel = "actions",
    inspector,
    record: selectedId,
    task: focusedItemId,
  } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const [draggingTask, setDraggingTask] = useState(false);
  const now = useTodayRefresh();
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
  const detail = inspector ?? (panel === "review" ? "summary" : undefined);
  const focusTask =
    plans.data?.find((item) => item.item_id === focusedItemId) ??
    plans.data?.[0];
  const openFocus = (id: string) => {
    if (!plans.data?.some((item) => item.item_id === id)) return;
    void navigate({
      search: (previous) => ({ ...previous, inspector: "focus", task: id }),
      resetScroll: false,
      replace: true,
    });
  };
  const setView = (next: string) =>
    void navigate({
      search: (previous) => ({
        ...previous,
        view: next === "orbit" ? "orbit" : "workbench",
        panel: "actions",
        inspector: undefined,
      }),
      replace: true,
    });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest(
          "input, textarea, select, [contenteditable=true], [role=dialog], [role=menu]",
        )
      )
        return;
      if (event.key === "Escape" && detail) {
        event.preventDefault();
        void navigate({
          search: (previous) => ({
            ...previous,
            panel: "actions",
            inspector: undefined,
          }),
          resetScroll: false,
          replace: true,
        });
        document
          .querySelector<HTMLButtonElement>(
            detail === "summary"
              ? `.today-pending [aria-controls="today-summary-preview"][aria-pressed="true"]`
              : "#today-focus-trigger",
          )
          ?.focus();
        return;
      }
      if (!event.ctrlKey || event.altKey || event.shiftKey || event.metaKey)
        return;
      if (event.key === "1" || event.key === "2") {
        event.preventDefault();
        void navigate({
          search: (previous) => ({
            ...previous,
            view: event.key === "2" ? "orbit" : "workbench",
            panel: "actions",
            inspector: undefined,
          }),
          replace: true,
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, detail]);
  useEffect(() => {
    if (!detail) return;
    const frame = window.requestAnimationFrame(() => {
      document
        .getElementById(
          detail === "summary" ? "today-summary-preview" : "today-focus-title",
        )
        ?.focus({ preventScroll: true });
      document
        .getElementById("today-pane-review")
        ?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [detail, selectedId, focusedItemId]);
  const date = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(now);

  return (
    <div className="today-workspace" data-dragging-task={draggingTask}>
      <Tabs
        value={view}
        onValueChange={(value) => setView(String(value))}
        className="today-workspace-tabs gap-0"
      >
        <header className="today-header flex flex-wrap items-center justify-between gap-3 px-4 py-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-headline font-headline">{t("today.title")}</h1>
            <p className="text-label text-ink-muted border-border-subtle border-l pl-3">
              {date}
            </p>
          </div>
          <TabsList className="h-auto max-w-full p-1">
            <TabsTrigger
              value="workbench"
              aria-keyshortcuts="Control+1"
              className="data-active:bg-primary data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground hover:bg-today-soft gap-2 px-3 py-1.5 focus-visible:ring-2"
            >
              {t("today.workspace.workbench")}
              <kbd className="text-label font-sans opacity-80">Ctrl 1</kbd>
            </TabsTrigger>
            <TabsTrigger
              value="orbit"
              aria-keyshortcuts="Control+2"
              className="data-active:bg-primary data-active:text-today-primary-foreground dark:data-active:bg-today-accent dark:data-active:text-today-primary-foreground hover:bg-today-soft gap-2 px-3 py-1.5 focus-visible:ring-2"
            >
              {t("today.workspace.orbit")}
              <kbd className="text-label font-sans opacity-80">Ctrl 2</kbd>
            </TabsTrigger>
          </TabsList>
          <div className="today-header-actions ml-auto flex flex-wrap items-center justify-end gap-3">
            <p className="text-label text-ink-muted flex items-center gap-2">
              <HardDrive className="size-4" aria-hidden="true" />
              {t("today.workspace.local")}
            </p>
            <Button
              size="sm"
              variant={detail === "focus" ? "secondary" : "ghost"}
              id="today-focus-trigger"
              title={t("today.workspace.dropFocus")}
              onDragOver={(event) => {
                if (
                  event.dataTransfer.types.includes(
                    "application/x-knowrealm-plan-item",
                  )
                ) {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "copy";
                }
              }}
              onDrop={(event) => {
                event.preventDefault();
                openFocus(
                  event.dataTransfer.getData(
                    "application/x-knowrealm-plan-item",
                  ),
                );
              }}
              aria-pressed={detail === "focus"}
              aria-controls="today-pane-review"
              onClick={() =>
                void navigate({
                  search: (previous) => ({ ...previous, inspector: "focus" }),
                  resetScroll: false,
                  replace: true,
                })
              }
            >
              <Timer aria-hidden="true" />
              {t("today.workspace.focus.title")}
            </Button>
          </div>
        </header>
        <div
          className="today-grid"
          onDragStart={(event) => {
            if (
              event.dataTransfer.types.includes(
                "application/x-knowrealm-plan-item",
              )
            )
              setDraggingTask(true);
          }}
          onDragEnd={() => setDraggingTask(false)}
          data-inspector={detail ?? "closed"}
          tabIndex={0}
          role="region"
          aria-label={t("today.workspace.workArea")}
        >
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
                selectedItemId={focusedItemId}
                onFocus={openFocus}
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
            id="today-pane-pending"
            aria-label={t("today.workspace.pending")}
            className="today-pending-workspace today-left"
            tabIndex={0}
          >
            <TodayPending
              summaries={pending.data ?? []}
              pending={pending.isPending}
              error={pending.isError}
              onRetry={() => void pending.refetch()}
              selectedId={selected?.record_id}
              onSelect={(id) => {
                void navigate({
                  search: (previous) => ({
                    ...previous,
                    record: id,
                    panel: "review",
                    inspector: "summary",
                  }),
                  resetScroll: false,
                  replace: true,
                });
              }}
            />
            <div
              className="today-assets-list"
              role="region"
              aria-label={t("today.recentAssets.title")}
              tabIndex={0}
            >
              <TodayAssets />
            </div>
          </aside>
          <aside
            id="today-pane-review"
            aria-label={t("today.rightRail.label")}
            className="today-rail min-w-0"
            data-detail={detail}
            tabIndex={0}
          >
            <div className="today-inspector-toolbar flex items-center justify-between gap-2 px-3 py-2">
              <p className="text-label text-ink-muted">
                {t(
                  detail === "summary"
                    ? "today.workspace.preview.tab"
                    : "today.workspace.focus.title",
                )}
              </p>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={t("today.workspace.closeInspector")}
                onClick={() => {
                  void navigate({
                    search: (previous) => ({
                      ...previous,
                      panel: "actions",
                      inspector: undefined,
                    }),
                    resetScroll: false,
                    replace: true,
                  });
                  document
                    .querySelector<HTMLButtonElement>(
                      detail === "summary"
                        ? `.today-pending [aria-controls="today-summary-preview"][aria-pressed="true"]`
                        : "#today-focus-trigger",
                    )
                    ?.focus();
                }}
              >
                <PanelRightClose aria-hidden="true" />
              </Button>
            </div>
            <div className="today-focus-slot">
              <TodayFocus task={focusTask} onDropTask={openFocus} />
            </div>
            <TodaySummaryPreview
              key={selected?.record_id ?? "sample"}
              record={selected}
              loading={pending.isPending}
              error={pending.isError}
              active={detail === "summary"}
            />
          </aside>
        </div>
      </Tabs>
    </div>
  );
}
