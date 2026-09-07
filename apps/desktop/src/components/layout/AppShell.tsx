import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import {
  Archive,
  BookOpenText,
  Bot,
  CalendarDays,
  ClipboardPaste,
  Inbox,
  Library,
  Mic,
  NotebookPen,
  Settings,
  Upload,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { AppearanceSync } from "@/features/settings/AppearanceSync";
import { useSavePreference } from "@/features/settings/PreferencesSection";
import { SidebarUserArea } from "@/components/layout/SidebarUserArea";
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
  { labelKey: "nav.library", icon: Library },
  { labelKey: "nav.profile", icon: UserRound },
  { labelKey: "nav.settings", icon: Settings, to: "/settings" },
] as const;

const captureItems = [
  { labelKey: "capture.note", icon: NotebookPen },
  { labelKey: "capture.paste", icon: ClipboardPaste },
  { labelKey: "capture.import", icon: Upload },
  { labelKey: "capture.record", icon: Mic },
] as const;

const activeNavClass =
  "flex h-9 items-center gap-3 rounded-md bg-surface-subtle px-3 text-body font-semibold text-ink-strong transition-colors focus-visible:ring-3 focus-visible:ring-ring/40 max-compact:justify-center max-compact:px-0";
const inactiveNavClass =
  "flex h-9 items-center gap-3 rounded-md px-3 text-body font-medium text-muted-foreground transition-colors hover:bg-surface-subtle hover:text-ink-strong focus-visible:ring-3 focus-visible:ring-ring/40 max-compact:justify-center max-compact:px-0";

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
  const [textCaptureFocusRequest, setTextCaptureFocusRequest] = useState(0);
  const [captureFeedback, setCaptureFeedback] = useState("");
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
  const { mutate: savePreference } = useSavePreference();
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
    if (!saved) return;
    if (restoreNavigationInFlightRef.current) {
      restoreNavigationInFlightRef.current = false;
      return;
    }
    if (pathname.startsWith("/settings")) return;
    const next = pathname === "/" ? null : pathname;
    if (next === saved.last_route) return;
    savePreference({ last_route: next });
  }, [pathname, preferences.data, savePreference]);
  // 关窗分流每次关窗时读取的最新偏好；偏好未载入时为 null = 不拦截直接退出。
  const closeBehaviorRef = useRef<CloseBehaviorPreference | null>(null);
  const closeBehavior = preferences.data?.close_behavior ?? null;
  useEffect(() => {
    closeBehaviorRef.current = closeBehavior;
  }, [closeBehavior]);
  const setRecordingOpen = useRecordingUiStore((state) => state.setStartOpen);
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
      setCaptureFeedback(t("capture.savedFeedback"));
    },
    [navigate, queryClient, t],
  );

  useEffect(() => {
    if (!captureFeedback) return;
    const timer = window.setTimeout(() => setCaptureFeedback(""), 5_000);
    return () => window.clearTimeout(timer);
  }, [captureFeedback]);

  return (
    <div className="bg-canvas text-foreground flex h-screen min-w-0 overflow-hidden">
      <AppearanceSync />
      <aside
        aria-label={t("nav.label")}
        className="w-sidebar bg-canvas max-compact:w-16 max-compact:px-2 flex h-screen shrink-0 flex-col px-3 py-4 transition-[width] duration-150"
      >
        <div className="max-compact:justify-center max-compact:px-0 flex h-10 items-center gap-3 px-3">
          <BookOpenText
            className="text-ink-strong size-5 shrink-0"
            aria-hidden="true"
          />
          <div className="max-compact:sr-only min-w-0">
            <p className="text-body text-ink-strong font-section truncate">
              {t("app.name")}
            </p>
            <p className="text-label text-muted-foreground truncate">
              {t("app.tagline")}
            </p>
          </div>
        </div>

        <nav className="mt-7 flex flex-col gap-1">
          {navigationItems.map((item) => {
            const { labelKey, icon: Icon } = item;
            const label = t(labelKey);

            if ("to" in item) {
              return (
                <Link
                  key={labelKey}
                  to={item.to}
                  activeOptions={{ exact: item.to === "/" }}
                  activeProps={{ className: activeNavClass }}
                  inactiveProps={{ className: inactiveNavClass }}
                  aria-label={label}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="max-compact:sr-only truncate">{label}</span>
                </Link>
              );
            }

            return (
              <Button
                key={labelKey}
                variant="ghost"
                size="lg"
                disabled
                className="max-compact:justify-center max-compact:px-0 w-full justify-start gap-3 px-3 disabled:pointer-events-auto disabled:opacity-70 disabled:hover:bg-transparent"
                aria-label={t("nav.unavailableLabel", { label })}
              >
                <Icon data-icon="inline-start" aria-hidden="true" />
                <span className="max-compact:sr-only truncate">{label}</span>
                <span className="text-label max-compact:sr-only ml-auto">
                  {t("nav.unavailable")}
                </span>
              </Button>
            );
          })}
        </nav>

        <SidebarUserArea />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          aria-label={t("capture.label")}
          className="h-topbar bg-paper px-content flex shrink-0 items-center justify-between gap-4"
        >
          <p className="text-label text-muted-foreground font-label">
            {t("capture.label")}
          </p>
          <div className="flex min-w-0 items-center gap-1">
            <RecordingExperience onAccepted={openRecord} />
            {captureItems.map(({ labelKey, icon: Icon }) => {
              const label = t(labelKey);
              const isRecord = labelKey === "capture.record";
              return (
                <Button
                  key={labelKey}
                  variant={isRecord ? "default" : "ghost"}
                  size="sm"
                  disabled={isRecord && recordingActive}
                  onClick={() => openCapture(labelKey)}
                  className={cn(
                    "disabled:pointer-events-auto disabled:opacity-70",
                    isRecord
                      ? "hover:bg-primary-hover"
                      : "disabled:hover:bg-transparent",
                  )}
                  aria-label={label}
                >
                  <Icon data-icon="inline-start" aria-hidden="true" />
                  <span className="max-compact:sr-only">{label}</span>
                </Button>
              );
            })}
          </div>
        </header>
        {captureFeedback ? (
          <p
            role="status"
            aria-live="polite"
            className="bg-paper px-content text-label text-muted-foreground pt-2"
          >
            {captureFeedback}
          </p>
        ) : null}
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
        <main className="bg-canvas min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
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
