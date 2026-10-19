import { useContext } from "react";
import { Link } from "@tanstack/react-router";
import {
  ClipboardCheck,
  MessagesSquare,
  PencilLine,
  Mic,
  Upload,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { TodayContinueLearning } from "@/features/today/components/TodayContinueLearning";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { cn } from "@/lib/utils";
import { CaptureActionsContext } from "@/components/layout/captureActionsContext";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";

export function TodayQuickStart({ showStats = true }: { showStats?: boolean }) {
  const { t } = useTranslation();
  const openQuickNote = useContext(QuickNoteContext);
  const openCapture = useContext(CaptureActionsContext);
  return (
    <div className="today-bottom-grid">
      <TodayContinueLearning />
      <section
        aria-labelledby="today-quick-title"
        className="today-panel today-quick-panel p-4"
      >
        <h2 id="today-quick-title" className="today-heading">
          <Zap className="size-4" aria-hidden="true" />
          {t("today.redesign.quickCapture")}
        </h2>
        <div className="today-capture-actions mt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => openQuickNote?.()}
            disabled={!openQuickNote}
          >
            <PencilLine aria-hidden="true" />
            {t("capture.note")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => openCapture?.("capture.import")}
            disabled={!openCapture}
          >
            <Upload aria-hidden="true" />
            {t("capture.import")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => openCapture?.("capture.record")}
            disabled={!openCapture}
          >
            <Mic aria-hidden="true" />
            {t("capture.record")}
          </Button>
        </div>
        <p className="text-label text-ink-muted mt-3">
          {t("today.workspace.noteHint")}
        </p>
      </section>
      <section
        aria-label={t("today.rightRail.assistantTitle")}
        className="today-panel today-assistant-panel p-4"
      >
        <div className="flex items-start gap-3">
          <MessagesSquare className="size-6 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <h3 className="text-body font-medium">
              {t("today.rightRail.assistantTitle")}
            </h3>
            <p className="text-label text-ink-muted mt-1">
              {t("today.workspace.askHint")}
            </p>
            <Link
              to="/chat"
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mt-3",
              )}
            >
              {t("today.workspace.startChat")}
            </Link>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <ClipboardCheck className="size-6 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <h3 className="text-body font-medium">
              {t("today.workspace.practice")}
            </h3>
            <p className="text-label text-ink-muted mt-1">
              {t("today.workspace.practiceHint")}
            </p>
            <Link
              to="/spaces"
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "mt-3",
              )}
            >
              {t("today.workspace.openPractice")}
            </Link>
          </div>
        </div>
      </section>
      {showStats && <TodayStatsBand compact />}
    </div>
  );
}
