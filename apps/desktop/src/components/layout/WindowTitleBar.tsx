import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  Copy,
  Minus,
  Square,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { getDesktopWindow } from "@/services/tauri/window";

const controlClass =
  "h-full w-12 rounded-none transition-none active:translate-y-0 active:bg-surface-strong focus-visible:ring-inset max-sm:w-10";

export function WindowTitleBar() {
  const { t } = useTranslation();
  const [appWindow] = useState(getDesktopWindow);
  const [state, setState] = useState({ focused: true, maximized: false });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!appWindow) return;
    let disposed = false;
    let revision = 0;
    const unlisteners: Array<() => void> = [];
    const syncState = async () => {
      const current = ++revision;
      try {
        const [focused, maximized] = await Promise.all([
          appWindow.isFocused(),
          appWindow.isMaximized(),
        ]);
        if (!disposed && current === revision) setState({ focused, maximized });
      } catch (cause) {
        console.error("Failed to read window state", cause);
        if (!disposed) setError(t("windowTitleBar.stateFailed"));
      }
    };

    void Promise.allSettled([
      appWindow.onResized(() => void syncState()),
      appWindow.onFocusChanged(() => void syncState()),
    ]).then((results) => {
      for (const result of results) {
        if (result.status === "fulfilled") {
          if (disposed) result.value();
          else unlisteners.push(result.value);
        } else {
          console.error("Failed to subscribe to window state", result.reason);
          if (!disposed) setError(t("windowTitleBar.stateFailed"));
        }
      }
      if (!disposed) void syncState();
    });

    return () => {
      disposed = true;
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, [appWindow, t]);

  const runAction = async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (cause) {
      console.error("Failed to control window", cause);
      setError(t("windowTitleBar.actionFailed"));
    }
  };

  const controls = [
    { label: "minimize", icon: Minus, action: () => appWindow?.minimize() },
    {
      label: state.maximized ? "restore" : "maximize",
      icon: state.maximized ? Copy : Square,
      action: () => appWindow?.toggleMaximize(),
    },
    { label: "close", icon: X, action: () => appWindow?.close() },
  ] as const;

  return (
    <header
      aria-label={t("windowTitleBar.label")}
      // Base UI 保留 live 区域的可访问性，窗口控件在模态弹层打开时仍需可用。
      aria-live="off"
      data-tauri-drag-region
      data-focused={state.focused}
      data-maximized={state.maximized}
      className="bg-canvas border-border-subtle text-ink h-titlebar data-[focused=false]:text-muted-foreground relative z-60 flex shrink-0 items-center border-b select-none"
    >
      <div
        data-tauri-drag-region
        className="flex h-full shrink-0 items-center gap-2 px-4 max-sm:px-3"
      >
        <BookOpenText
          aria-hidden="true"
          className="pointer-events-none size-4"
        />
        <span className="text-label font-section pointer-events-none max-sm:hidden">
          {t("app.name")}
        </span>
      </div>
      <div
        role="group"
        aria-label={t("windowTitleBar.menu")}
        className="flex shrink-0 items-center"
      >
        {(["file", "edit", "view", "help"] as const).map((menu) => (
          <Button
            key={menu}
            variant="ghost"
            size="sm"
            disabled
            title={t("windowTitleBar.placeholder")}
            className="max-sm:text-label max-sm:px-1.5"
          >
            {t(`windowTitleBar.${menu}`)}
          </Button>
        ))}
      </div>
      <div
        role="group"
        aria-label={t("windowTitleBar.navigation")}
        className="border-border-subtle ml-3 flex shrink-0 gap-1 border-l pl-3 max-sm:ml-1 max-sm:pl-1"
      >
        <Button
          variant="ghost"
          size="icon-sm"
          disabled
          aria-label={t("windowTitleBar.back")}
          title={t("windowTitleBar.placeholder")}
        >
          <ArrowLeft aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled
          aria-label={t("windowTitleBar.forward")}
          title={t("windowTitleBar.placeholder")}
        >
          <ArrowRight aria-hidden="true" />
        </Button>
      </div>
      <div
        data-tauri-drag-region
        className="h-full min-w-4 flex-1 overflow-hidden px-3"
      >
        {error ? (
          <p
            role="alert"
            className="text-label text-destructive pointer-events-none flex h-full items-center truncate"
            title={error}
          >
            {error}
          </p>
        ) : null}
      </div>
      <div
        role="group"
        aria-label={t("windowTitleBar.controls")}
        className="flex h-full shrink-0"
        onMouseDown={(event) => event.preventDefault()}
      >
        {controls.map(({ label, icon: Icon, action }) => (
          <Button
            key={label}
            variant="ghost"
            className={`${controlClass} ${label === "close" ? "hover:bg-destructive dark:hover:bg-destructive active:bg-destructive hover:text-primary-foreground" : ""}`}
            disabled={!appWindow}
            aria-label={t(`windowTitleBar.${label}`)}
            title={t(`windowTitleBar.${label}`)}
            onClick={() =>
              void runAction(async () => {
                await action();
              })
            }
          >
            <Icon aria-hidden="true" className="size-3.5" />
          </Button>
        ))}
      </div>
    </header>
  );
}
