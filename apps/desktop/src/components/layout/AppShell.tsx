import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import {
  Archive,
  BookOpenText,
  Bot,
  CalendarDays,
  Inbox,
  Library,
  Mic,
  NotebookPen,
  Upload,
  UserRound,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { DocumentImportDialog } from "@/features/document-import/DocumentImportDialog";
import { RecordingExperience } from "@/features/recording/RecordingExperience";
import {
  blocksNewRecording,
  useRecordingSessions,
} from "@/features/recording/api/queries";
import { useRecordingUiStore } from "@/features/recording/store";
import { cn } from "@/lib/utils";

const navigationItems = [
  { labelKey: "nav.today", icon: CalendarDays, to: "/" },
  { labelKey: "nav.inbox", icon: Inbox },
  { labelKey: "nav.spaces", icon: Archive, to: "/spaces" },
  { labelKey: "nav.chat", icon: Bot },
  { labelKey: "nav.library", icon: Library },
  { labelKey: "nav.profile", icon: UserRound },
] as const;

const captureItems = [
  { labelKey: "capture.note", icon: NotebookPen, available: false },
  { labelKey: "capture.import", icon: Upload, available: true },
  { labelKey: "capture.record", icon: Mic, available: true },
] as const;

const activeNavClass =
  "flex h-9 items-center gap-3 rounded-md bg-surface-subtle px-3 text-body font-semibold text-ink-strong transition-colors focus-visible:ring-3 focus-visible:ring-ring/40 max-compact:justify-center max-compact:px-0";
const inactiveNavClass =
  "flex h-9 items-center gap-3 rounded-md px-3 text-body font-medium text-muted-foreground transition-colors hover:bg-surface-subtle hover:text-ink-strong focus-visible:ring-3 focus-visible:ring-ring/40 max-compact:justify-center max-compact:px-0";

export function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [importOpen, setImportOpen] = useState(false);
  const setRecordingOpen = useRecordingUiStore((state) => state.setStartOpen);
  const recordingSessions = useRecordingSessions();
  const recordingActive = (recordingSessions.data ?? []).some(
    blocksNewRecording,
  );

  const openCapture = (labelKey: (typeof captureItems)[number]["labelKey"]) => {
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

  return (
    <div className="bg-canvas text-foreground flex h-screen min-w-0 overflow-hidden">
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
            {captureItems.map(({ labelKey, icon: Icon, available }) => {
              const label = t(labelKey);
              return (
                <Button
                  key={labelKey}
                  variant={labelKey === "capture.record" ? "default" : "ghost"}
                  size="sm"
                  disabled={
                    !available ||
                    (labelKey === "capture.record" && recordingActive)
                  }
                  onClick={available ? () => openCapture(labelKey) : undefined}
                  className={cn(
                    "disabled:pointer-events-auto disabled:opacity-70",
                    labelKey === "capture.record"
                      ? "hover:bg-primary-hover"
                      : "disabled:hover:bg-transparent",
                  )}
                  aria-label={
                    available ? label : t("nav.unavailableLabel", { label })
                  }
                >
                  <Icon data-icon="inline-start" aria-hidden="true" />
                  <span className="max-compact:sr-only">{label}</span>
                  {available ? null : (
                    <span className="text-label max-compact:sr-only">
                      {t("nav.unavailable")}
                    </span>
                  )}
                </Button>
              );
            })}
          </div>
        </header>
        <main className="bg-paper min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <DocumentImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onAccepted={openRecord}
      />
    </div>
  );
}
