import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import {
  Archive,
  BookOpenText,
  Bot,
  CalendarDays,
  ChevronDown,
  ClipboardPaste,
  Inbox,
  Library,
  Mic,
  NotebookPen,
  Search,
  Settings,
  Upload,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AppTooltip } from "@/components/common/AppTooltip";
import { AppToasts } from "@/components/common/AppToast";
import { appToast } from "@/components/common/appToastManager";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DocumentImportDialog } from "@/features/document-import/DocumentImportDialog";
import { RecordingExperience } from "@/features/recording/RecordingExperience";
import { CommandPalette } from "@/features/search/components/CommandPalette";
import { AppearanceSync } from "@/features/settings/AppearanceSync";
import { useSavePreference } from "@/features/settings/useSavePreference";
import { SidebarUserArea } from "@/components/layout/SidebarUserArea";
import { SidebarResizeHandle } from "@/components/layout/SidebarResizeHandle";
import {
  APP_SIDEBAR_ID,
  useSidebarUiStore,
} from "@/components/layout/sidebarUiStore";
import { selectSidebarCourses } from "@/components/layout/selectSidebarCourses";
import { useActiveCourses } from "@/features/courses/api/queries";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import {
  blocksNewRecording,
  useRecordingSessions,
} from "@/features/recording/api/queries";
import { recordingKeys } from "@/features/recording/api/keys";
import { recordingApi } from "@/features/recording/api/recordings";
import { useRecordingUiStore } from "@/features/recording/store";
import { recordKeys } from "@/features/records/api/keys";
import type {
  TextCaptureAccepted,
  TextCaptureMode,
} from "@/features/text-capture/api/textCaptures";
import { TextCaptureDialog } from "@/features/text-capture/TextCaptureDialog";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { cn } from "@/lib/utils";
import { isRestartPending } from "@/services/restartPending";
import {
  exitApplication,
  isDesktopLifecycleAvailable,
  listenExitRequested,
} from "@/services/tauri/lifecycle";
import {
  mountCloseBehavior,
  mountQuickNoteShortcut,
  type CloseBehaviorPreference,
} from "@/services/tauri/preferences";

const navigationItems = [
  { labelKey: "nav.today", icon: CalendarDays, to: "/" },
  { labelKey: "nav.inbox", icon: Inbox, to: "/inbox" },
  { labelKey: "nav.spaces", icon: Archive, to: "/spaces" },
  { labelKey: "nav.chat", icon: Bot, to: "/chat" },
  { labelKey: "nav.library", icon: Library, to: "/library" },
  { labelKey: "nav.profile", icon: UserRound },
] as const;

const captureItems = [
  { labelKey: "capture.note", icon: NotebookPen },
  { labelKey: "capture.paste", icon: ClipboardPaste },
  { labelKey: "capture.import", icon: Upload },
  { labelKey: "capture.record", icon: Mic },
] as const;

const activeNavClass =
  "flex h-9 items-center gap-3 overflow-hidden rounded-md bg-surface-subtle px-3 text-body font-semibold text-ink-strong transition-colors focus-visible:ring-3 focus-visible:ring-ring/40";
const inactiveNavClass =
  "flex h-9 items-center gap-3 overflow-hidden rounded-md px-3 text-body font-medium text-muted-foreground transition-colors hover:bg-surface-subtle hover:text-ink-strong focus-visible:ring-3 focus-visible:ring-ring/40";

type ExitRisks = {
  recording: boolean;
  unsavedText: boolean;
};

export function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [textCapture, setTextCapture] = useState<TextCaptureMode | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [textCaptureFocusRequest, setTextCaptureFocusRequest] = useState(0);
  const [coursesExpanded, setCoursesExpanded] = useState(true);
  const [shortcutUnavailable, setShortcutUnavailable] = useState<string | null>(
    null,
  );
  const [lifecycleError, setLifecycleError] = useState("");
  const [exitRisks, setExitRisks] = useState<ExitRisks | null>(null);
  const [exitPending, setExitPending] = useState(false);
  const textCaptureDirtyRef = useRef(false);
  const exitCheckPendingRef = useRef(false);
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });
  // 上次界面恢复：偏好首次到达且仍停在默认页时回上次路由（桌面启动总落默认页；
  // 该前提同时保证显式打开的路径不被恢复覆盖）。设置页路由不参与记忆，目标不存在
  // 由现有 NotFound 兜底。恢复导航造成的路径变化由 in-flight 标记挡住，不触发写入；
  // 恢复只尝试一次，之后的路径变化都按普通导航记忆。偏好载入前的导航不记忆（启动
  // 间隙极短，同快捷键的间隙取舍）。写入走 useMutation 但不消费 error：路由记忆
  // 非用户发起的编辑，失败只损失一次恢复，不值得一处全局打扰。
  const pathname = useLocation({ select: (location) => location.pathname });
  const activeCourses = useActiveCourses();
  const activeCourseId = pathname.match(/^\/spaces\/([^/]+)/)?.[1];
  const sidebarCourses = selectSidebarCourses(
    activeCourses.courses,
    activeCourseId,
  );
  const { mutate: savePreference, isPending: preferenceSavePending } =
    useSavePreference();
  const lastRouteAttemptRef = useRef<string | null | undefined>(undefined);
  const restoreAttemptedRef = useRef(false);
  const restoreNavigationInFlightRef = useRef(false);
  useEffect(() => {
    if (restoreAttemptedRef.current) return;
    const lastRoute = preferences.data?.last_route;
    if (lastRoute === undefined) return;
    restoreAttemptedRef.current = true;
    if (lastRoute && lastRoute !== pathname && pathname === "/") {
      restoreNavigationInFlightRef.current = true;
      void navigate({ to: lastRoute, replace: true });
    }
  }, [navigate, pathname, preferences.data]);
  useEffect(() => {
    const saved = preferences.data;
    if (!saved || preferenceSavePending) return;
    if (restoreNavigationInFlightRef.current) {
      restoreNavigationInFlightRef.current = false;
      return;
    }
    if (pathname.startsWith("/settings")) return;
    const next = pathname === "/" ? null : pathname;
    if (next === saved.last_route || next === lastRouteAttemptRef.current)
      return;
    lastRouteAttemptRef.current = next;
    savePreference({ last_route: next });
  }, [pathname, preferences.data, savePreference, preferenceSavePending]);
  // 关窗分流每次关窗时读取的最新偏好；偏好未载入时为 null = 不拦截直接退出。
  const closeBehaviorRef = useRef<CloseBehaviorPreference | null>(null);
  const closeBehavior = preferences.data?.close_behavior ?? null;
  useEffect(() => {
    closeBehaviorRef.current = closeBehavior;
  }, [closeBehavior]);
  const setRecordingOpen = useRecordingUiStore((state) => state.setStartOpen);
  const sidebarCollapsed = useSidebarUiStore((state) => state.collapsed);
  const sidebarWidth = useSidebarUiStore((state) => state.width);
  const recordingSessions = useRecordingSessions();
  const recordingActive = (recordingSessions.data ?? []).some(
    blocksNewRecording,
  );

  const openQuickNote = useCallback(() => {
    setTextCapture((current) => current ?? "QUICK_NOTE");
    setTextCaptureFocusRequest((current) => current + 1);
  }, []);

  const requestSafeExit = useCallback(async () => {
    if (exitCheckPendingRef.current) return;
    exitCheckPendingRef.current = true;
    setLifecycleError("");
    try {
      // 数据目录迁移已停止 sidecar：后端不存在、无录音可保护，跳过状态检查，
      // 否则查询失败会让"取消退出以保护数据"把退出永久卡死。
      const sessions = isRestartPending()
        ? []
        : await queryClient.fetchQuery({
            queryKey: recordingKeys.unfinished(),
            queryFn: recordingApi.list,
            staleTime: 0,
          });
      const risks = {
        recording: sessions.some(blocksNewRecording),
        unsavedText: textCaptureDirtyRef.current,
      };
      if (risks.recording || risks.unsavedText) {
        setExitRisks(risks);
      } else {
        await exitApplication();
      }
    } catch {
      setLifecycleError(t("desktopLifecycle.exitCheckFailed"));
    } finally {
      exitCheckPendingRef.current = false;
    }
  }, [queryClient, t]);

  useEffect(() => {
    if (!isDesktopLifecycleAvailable()) return;
    let disposed = false;
    const unlisteners: Array<() => void> = [];

    void Promise.allSettled([
      listenExitRequested(() => void requestSafeExit()),
      mountCloseBehavior({
        getBehavior: () => closeBehaviorRef.current,
        onExitRequested: () => void requestSafeExit(),
      }),
    ]).then((results) => {
      const registered = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : [],
      );
      if (disposed) registered.forEach((unlisten) => unlisten());
      else unlisteners.push(...registered);
      if (!disposed && results.some((result) => result.status === "rejected"))
        setLifecycleError(t("desktopLifecycle.initFailed"));
    });

    return () => {
      disposed = true;
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, [requestSafeExit, t]);

  // 速记快捷键注册点在前端：偏好到达后按其值注册，回调直开速记框；
  // 启动间隙（偏好未载入）快捷键不可用；改键成功后缓存刷新重挂由包装按键去重。
  const quickNoteShortcut = preferences.data?.quick_note_shortcut ?? null;
  useEffect(() => {
    if (!isDesktopLifecycleAvailable() || !quickNoteShortcut) return;
    let disposed = false;
    void mountQuickNoteShortcut(quickNoteShortcut, openQuickNote).then(
      (registered) => {
        if (disposed) return;
        setShortcutUnavailable(registered ? null : quickNoteShortcut);
      },
    );
    return () => {
      disposed = true;
    };
  }, [quickNoteShortcut, openQuickNote]);

  const confirmExit = useCallback(async () => {
    if (exitPending) return;
    setExitPending(true);
    setLifecycleError("");
    try {
      await exitApplication();
    } catch {
      setLifecycleError(t("desktopLifecycle.exitFailed"));
      setExitPending(false);
      setExitRisks(null);
    }
  }, [exitPending, t]);

  const openCapture = (labelKey: (typeof captureItems)[number]["labelKey"]) => {
    if (labelKey === "capture.note") openQuickNote();
    if (labelKey === "capture.paste") setTextCapture("PASTE");
    if (labelKey === "capture.import") setImportOpen(true);
    if (labelKey === "capture.record") setRecordingOpen(true);
  };

  const openRecord = useCallback(
    ({ record_id }: { record_id: string }) =>
      navigate({
        to: "/records/$recordId",
        params: { recordId: record_id },
        search: { tab: "transcript" },
      }),
    [navigate],
  );

  const handleTextAccepted = useCallback(
    async (result: TextCaptureAccepted, courseSelected: boolean) => {
      if (courseSelected) {
        await navigate({
          to: "/records/$recordId",
          params: { recordId: result.record_id },
        });
        return;
      }
      await queryClient.invalidateQueries({ queryKey: recordKeys.inbox() });
      appToast.add({ description: t("capture.savedFeedback") });
    },
    [navigate, queryClient, t],
  );

  return (
    <div className="bg-canvas text-foreground max-compact:p-0 flex h-full min-w-0 overflow-hidden p-2">
      <AppearanceSync />
      <AppToasts />
      <aside
        id={APP_SIDEBAR_ID}
        aria-label={t("nav.label")}
        inert={sidebarCollapsed}
        style={
          {
            "--sidebar-width":
              sidebarWidth === null ? undefined : `${sidebarWidth}px`,
          } as CSSProperties
        }
        className={cn(
          "app-sidebar bg-sidebar relative flex h-full shrink-0 transition-[width] duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]",
          sidebarCollapsed ? "w-0 overflow-hidden" : "w-[var(--sidebar-width)]",
        )}
      >
        {/* Toggle 只裁切，内容与导航保持挂载；容器宽度决定文字可见性。 */}
        <div
          className={cn(
            "sidebar-content flex h-full w-[var(--sidebar-width)] shrink-0 flex-col overflow-x-hidden overflow-y-auto px-2 py-3 transition-opacity duration-150",
            sidebarCollapsed && "opacity-0",
          )}
        >
          <div className="flex h-10 shrink-0 items-center gap-3 overflow-hidden px-3">
            <BookOpenText
              className="text-ink-strong size-5 shrink-0"
              aria-hidden="true"
            />
            <div className="sidebar-label min-w-0">
              <p className="text-body text-ink-strong font-section truncate">
                {t("app.name")}
              </p>
              <p className="text-label text-muted-foreground truncate">
                {t("app.tagline")}
              </p>
            </div>
          </div>

          <nav className="mt-5 flex flex-col gap-1">
            {navigationItems.map((item) => {
              const { labelKey, icon: Icon } = item;
              const label = t(labelKey);

              if ("to" in item) {
                return (
                  <AppTooltip key={labelKey} label={label}>
                    <Link
                      to={item.to}
                      activeOptions={{ exact: item.to === "/" }}
                      activeProps={{ className: activeNavClass }}
                      inactiveProps={{ className: inactiveNavClass }}
                      aria-label={label}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden="true" />
                      <span className="sidebar-label truncate">{label}</span>
                    </Link>
                  </AppTooltip>
                );
              }

              return (
                <AppTooltip
                  key={labelKey}
                  label={t("nav.unavailableLabel", { label })}
                >
                  <Button
                    variant="ghost"
                    size="lg"
                    disabled
                    className="w-full justify-start gap-3 overflow-hidden px-3 disabled:pointer-events-auto disabled:opacity-70 disabled:hover:bg-transparent"
                    aria-label={t("nav.unavailableLabel", { label })}
                  >
                    <Icon data-icon="inline-start" aria-hidden="true" />
                    <span className="sidebar-label truncate">{label}</span>
                    <span className="sidebar-label text-label ml-auto">
                      {t("nav.unavailable")}
                    </span>
                  </Button>
                </AppTooltip>
              );
            })}
          </nav>

          <section
            className="sidebar-courses mt-6 min-h-0 overflow-y-auto"
            aria-label={t("nav.courses.label")}
          >
            <button
              type="button"
              className="text-label text-ink-muted flex h-8 w-full items-center justify-between px-3 font-medium"
              aria-expanded={coursesExpanded}
              onClick={() => setCoursesExpanded((expanded) => !expanded)}
            >
              {t("nav.courses.label")}
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  "size-3.5 transition-transform",
                  coursesExpanded && "rotate-180",
                )}
              />
            </button>
            {coursesExpanded ? (
              activeCourses.isError ? (
                <p className="text-label text-ink-faint px-3 py-2">
                  {t("nav.courses.unavailable")}
                </p>
              ) : (
                <div className="mt-1 grid min-w-0 gap-0.5">
                  {sidebarCourses.map((course) => (
                    <Link
                      key={course.id}
                      to="/spaces/$courseId"
                      params={{ courseId: course.id }}
                      search={{ tab: "overview" }}
                      className="text-body-dense text-ink-muted hover:bg-surface-subtle hover:text-ink-strong focus-visible:ring-ring/40 flex h-8 min-w-0 items-center gap-2 rounded-sm px-3 focus-visible:ring-2"
                      activeProps={{
                        className:
                          "bg-surface-subtle text-ink-strong font-medium",
                      }}
                      title={course.name}
                    >
                      <span className="bg-border-strong size-1.5 shrink-0 rounded-full" />
                      <span className="truncate">{course.name}</span>
                    </Link>
                  ))}
                  {activeCourses.isPending ? (
                    <p className="text-label text-ink-faint px-3 py-2">
                      {t("nav.courses.loading")}
                    </p>
                  ) : null}
                  <Link
                    to="/spaces"
                    className="text-label text-ink-muted hover:text-ink-strong mt-1 px-3 py-1.5"
                  >
                    {t("nav.courses.viewAll")}
                  </Link>
                </div>
              )
            ) : null}
          </section>

          <SidebarUserArea />
          <AppTooltip label={t("nav.settings")}>
            <Link
              to="/settings"
              className="hover:bg-surface-subtle focus-visible:ring-ring/40 text-body text-muted-foreground mt-1 flex h-9 shrink-0 items-center gap-3 overflow-hidden rounded-md px-3 font-medium focus-visible:ring-3"
              aria-label={t("nav.settings")}
            >
              <Settings className="size-4 shrink-0" aria-hidden="true" />
              <span className="sidebar-label truncate">
                {t("nav.settings")}
              </span>
            </Link>
          </AppTooltip>
        </div>
        {!sidebarCollapsed && <SidebarResizeHandle />}
      </aside>

      <div className="bg-paper border-border-subtle max-compact:rounded-none max-compact:border-y-0 max-compact:border-r-0 flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border">
        <header
          aria-label={t("capture.label")}
          className="h-topbar border-border-subtle px-content flex shrink-0 items-center justify-between gap-4 border-b"
        >
          <div className="flex min-w-0 items-center gap-1">
            <RecordingExperience onAccepted={openRecord} />
            {captureItems.map(({ labelKey, icon: Icon }) => {
              const label = t(labelKey);
              const isRecord = labelKey === "capture.record";
              return (
                <Button
                  key={labelKey}
                  variant="ghost"
                  size="sm"
                  disabled={isRecord && recordingActive}
                  onClick={() => openCapture(labelKey)}
                  className={cn(
                    "disabled:pointer-events-auto disabled:opacity-70",
                    "disabled:hover:bg-transparent",
                  )}
                  aria-label={label}
                >
                  <Icon data-icon="inline-start" aria-hidden="true" />
                  <span className="max-compact:sr-only">{label}</span>
                </Button>
              );
            })}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPaletteOpen(true)}
            aria-label={t("commandPalette.openButton")}
            aria-keyshortcuts="Control+K"
            className="text-ink-muted min-w-24 justify-between"
          >
            <Search data-icon="inline-start" aria-hidden="true" />
            <span className="text-label font-label">
              {t("commandPalette.shortcutBadge")}
            </span>
          </Button>
        </header>
        {shortcutUnavailable ? (
          <Alert className="mx-content mb-2 w-auto">
            <AlertDescription>
              {t("desktopLifecycle.shortcutUnavailable", {
                shortcut: shortcutUnavailable,
              })}
            </AlertDescription>
          </Alert>
        ) : null}
        {lifecycleError ? (
          <Alert variant="destructive" className="mx-content mb-2 w-auto">
            <AlertDescription>{lifecycleError}</AlertDescription>
          </Alert>
        ) : null}
        <main className="bg-paper min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <QuickNoteContext value={openQuickNote}>
            <Outlet />
          </QuickNoteContext>
        </main>
      </div>
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onCaptureCommand={openCapture}
      />
      <DocumentImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onAccepted={openRecord}
      />
      {textCapture ? (
        <TextCaptureDialog
          open
          onOpenChange={(open) => {
            if (!open) setTextCapture(null);
          }}
          captureType={textCapture}
          focusRequest={textCaptureFocusRequest}
          onDirtyChange={(dirty) => {
            textCaptureDirtyRef.current = dirty;
          }}
          onAccepted={handleTextAccepted}
        />
      ) : null}
      <Dialog
        open={exitRisks !== null}
        onOpenChange={(open) => {
          if (!open && !exitPending) setExitRisks(null);
        }}
      >
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{t("desktopLifecycle.exitTitle")}</DialogTitle>
            <DialogDescription>
              {t("desktopLifecycle.exitDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="text-body text-foreground flex flex-col gap-2">
            {exitRisks?.recording ? (
              <p>{t("desktopLifecycle.recordingRisk")}</p>
            ) : null}
            {exitRisks?.unsavedText ? (
              <p>{t("desktopLifecycle.textRisk")}</p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={exitPending}
              onClick={() => setExitRisks(null)}
            >
              {t("desktopLifecycle.cancelExit")}
            </Button>
            <Button
              variant="destructive"
              disabled={exitPending}
              onClick={() => void confirmExit()}
            >
              {t("desktopLifecycle.confirmExit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
