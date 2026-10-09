import { useContext } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  MessagesSquare,
  PencilLine,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusTag } from "@/components/common/StatusTag";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { cn } from "@/lib/utils";

export function TodayQuickStart() {
  const { t } = useTranslation();
  const openQuickNote = useContext(QuickNoteContext);
  return (
    <>
      <section className="today-panel bg-today-soft flex flex-wrap items-center gap-3 p-4">
        <BookOpen className="size-6 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-label font-medium">
              {t("today.overview.continueTitle")}
            </h2>
            <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          </div>
          <p className="text-body mt-1 font-medium">
            {t("today.overview.continueItem")}
          </p>
          <p className="text-label text-ink-muted mt-1">
            {t("today.workspace.continueHint")}
          </p>
        </div>
        <Link
          to="/spaces"
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "text-today-accent",
          )}
        >
          {t("today.overview.openCourses")}
          <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </Link>
      </section>
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
