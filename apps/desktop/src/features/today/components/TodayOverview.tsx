import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { HardDrive, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { todayKeys } from "@/features/today/api/keys";
import { todayApi } from "@/features/today/api/today";
import { TodayActions } from "@/features/today/components/TodayActions";
import { TodayStudyMaterials } from "@/features/today/components/TodayStudyMaterials";
import { TodayMaterialPreparation } from "@/features/today/components/TodayMaterialPreparation";
import { TodayFocus } from "@/features/today/components/TodayFocus";
import { TodayPending } from "@/features/today/components/TodayPending";
import { TodayQuickStart } from "@/features/today/components/TodayQuickStart";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";
import { useTodayRefresh } from "@/features/today/useTodayRefresh";
import "@/features/today/components/TodayWorkspace.css";
import { Button } from "@/components/ui/button";

export function TodayOverview() {
  const { t, i18n } = useTranslation();
  const {
    view = "workbench",
    inspector,
    task: focusedItemId,
  } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const [materialIndex, setMaterialIndex] = useState(0);
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
  const detail = inspector;
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
        document.getElementById("today-focus-trigger")?.focus();
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
        .getElementById("today-focus-title")
        ?.focus({ preventScroll: true });
      document
        .getElementById("today-focus-title")
        ?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [detail, focusedItemId]);
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
              className="data-active:bg-today-tab-selected data-active:text-today-primary-foreground dark:data-active:bg-today-tab-selected dark:data-active:text-today-primary-foreground hover:bg-today-soft gap-2 px-3 py-1.5 focus-visible:ring-2"
            >
              {t("today.workspace.workbench")}
              <kbd className="text-label font-sans opacity-80">Ctrl 1</kbd>
            </TabsTrigger>
            <TabsTrigger
              value="orbit"
              aria-keyshortcuts="Control+2"
              className="data-active:bg-today-tab-selected data-active:text-today-primary-foreground dark:data-active:bg-today-tab-selected dark:data-active:text-today-primary-foreground hover:bg-today-soft gap-2 px-3 py-1.5 focus-visible:ring-2"
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
              aria-controls="today-focus-title"
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
          className="today-page-scroll"
          tabIndex={0}
          role="region"
          aria-label={t("today.workspace.workArea")}
        >
          <TabsContent value={view} keepMounted className="m-0">
            {view === "orbit" && (
              <div className="today-orbit">
                <TodayStatsBand />
              </div>
            )}
            <div
              className="today-grid"
              data-inspector={detail ?? "closed"}
              onDragStart={(event) => {
                if (
                  event.dataTransfer.types.includes(
                    "application/x-knowrealm-plan-item",
                  )
                )
                  setDraggingTask(true);
              }}
              onDragEnd={() => setDraggingTask(false)}
            >
              <div id="today-pane-actions" className="today-task-column">
                <TodayActions
                  summaries={pending.data}
                  loading={pending.isPending}
                  error={pending.isError}
                  onRetry={() => void pending.refetch()}
                  selectedItemId={focusTask?.item_id}
                  onFocus={openFocus}
                />
              </div>
              <div className="today-focus-column">
                <TodayFocus
                  task={focusTask}
                  onDropTask={openFocus}
                  onNextTask={
                    plans.data && plans.data.length > 1
                      ? () => {
                          const items = plans.data;
                          if (!items?.length) return;
                          const index = items.findIndex(
                            (item) => item.item_id === focusTask?.item_id,
                          );
                          openFocus(items[(index + 1) % items.length].item_id);
                        }
                      : undefined
                  }
                />
                <TodayStudyMaterials
                  selected={materialIndex}
                  onSelect={setMaterialIndex}
                />
              </div>
              <aside
                id="today-pane-pending"
                aria-label={t("today.workspace.pending")}
                className="today-pending-workspace"
              >
                <TodayMaterialPreparation />
                <TodayPending
                  summaries={pending.data ?? []}
                  pending={pending.isPending}
                  error={pending.isError}
                  onRetry={() => void pending.refetch()}
                />
              </aside>
            </div>
            <TodayQuickStart showStats={view !== "orbit"} />
          </TabsContent>
          <footer className="today-footer text-label text-ink-muted">
            <HardDrive className="size-3.5" aria-hidden="true" />
            {t("today.workspace.local")}
            <span aria-hidden="true">·</span>
            {t("today.redesign.footerHint")}
          </footer>
        </div>
      </Tabs>
    </div>
  );
}
