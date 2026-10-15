import { useContext } from "react";
import { Link } from "@tanstack/react-router";
import { ClipboardCheck, MessagesSquare, PencilLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { TodayContinueLearning } from "@/features/today/components/TodayContinueLearning";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { cn } from "@/lib/utils";

export function TodayQuickStart() {
  const { t } = useTranslation();
  const openQuickNote = useContext(QuickNoteContext);
  return (
    <>
      <TodayContinueLearning />
      <section aria-labelledby="today-quick-title" className="today-panel p-4">
        <h2 id="today-quick-title" className="today-heading">
          {t("today.workspace.quickStart")}
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="flex items-start gap-3">
            <PencilLine className="size-6 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <h3 className="text-body font-medium">{t("capture.note")}</h3>
              <p className="text-label text-ink-muted mt-1">
                {t("today.workspace.noteHint")}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => openQuickNote?.()}
                disabled={!openQuickNote}
              >
                {t("today.workspace.newNote")}
              </Button>
            </div>
          </div>
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
        </div>
      </section>
    </>
  );
}
