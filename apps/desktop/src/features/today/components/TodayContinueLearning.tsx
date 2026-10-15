import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ClipboardCheck, MessagesSquare, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { todayKeys } from "@/features/today/api/keys";
import {
  resumeApi,
  useLearningResumeActions,
} from "@/features/today/api/resume";
import { LearningResumeLink } from "@/features/today/components/LearningResumeLink";

const icons = {
  RECORD: BookOpen,
  QUIZ_TEST: ClipboardCheck,
  CHAT_SESSION: MessagesSquare,
};

export function TodayContinueLearning() {
  const { t, i18n } = useTranslation();
  const [confirmClear, setConfirmClear] = useState(false);
  const history = useQuery({
    queryKey: todayKeys.continueLearning,
    queryFn: resumeApi.list,
    staleTime: 0,
  });
  const mutation = useLearningResumeActions();
  const entries = history.data ?? [];
  return (
    <section
      aria-labelledby="today-continue-title"
      className="today-panel bg-today-soft p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 id="today-continue-title" tabIndex={-1} className="today-heading">
          {t("today.overview.continueTitle")}
        </h2>
        {entries.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            disabled={mutation.isPending}
            onClick={() => setConfirmClear(true)}
          >
            {t("today.resume.clear")}
          </Button>
        )}
      </div>
      {history.isPending ? (
        <p role="status" className="text-label text-ink-muted mt-3">
          {t("today.loading")}
        </p>
      ) : history.isError ? (
        <div role="alert" className="mt-3">
          <p className="text-label">{t("today.resume.loadFailed")}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => void history.refetch()}
          >
            {t("today.retry")}
          </Button>
        </div>
      ) : entries.length === 0 ? (
        <p className="text-label text-ink-muted mt-3">
          {t("today.resume.empty")}
        </p>
      ) : (
        <ul className="divide-border-subtle mt-2 divide-y">
          {entries.map((entry) => {
            const Icon = icons[entry.kind];
            const title =
              entry.title?.trim() || t(`today.resume.fallback.${entry.kind}`);
            return (
              <li
                key={`${entry.kind}:${entry.target_id}`}
                className="flex min-w-0 flex-wrap items-center gap-3 py-3"
              >
                <Icon aria-hidden="true" className="size-5 shrink-0" />
                <div className="min-w-0 flex-1 basis-40">
                  <p className="text-body truncate font-medium" title={title}>
                    {title}
                  </p>
                  <p className="text-label text-ink-muted mt-1 break-words">
                    {t(`today.resume.types.${entry.kind}`)}
                    {entry.course_name ? ` · ${entry.course_name}` : ""} ·{" "}
                    {t("today.resume.lastOpened", {
                      time: new Intl.DateTimeFormat(i18n.language, {
                        month: "numeric",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      }).format(new Date(entry.visited_at)),
                    })}
                  </p>
                  {entry.kind === "QUIZ_TEST" && (
                    <p className="text-label text-ink-muted mt-1 tabular-nums">
                      {t("today.resume.answers", {
                        answered: entry.answered_count,
                        total: entry.total_count,
                      })}
                    </p>
                  )}
                </div>
                <LearningResumeLink
                  target={entry}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  {t(`today.resume.continue.${entry.kind}`)}
                </LearningResumeLink>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("today.resume.remove", { title })}
                  disabled={mutation.isPending}
                  onClick={() =>
                    mutation.mutate(
                      {
                        action: "remove",
                        kind: entry.kind,
                        target_id: entry.target_id,
                      },
                      {
                        onSuccess: () =>
                          document
                            .getElementById("today-continue-title")
                            ?.focus(),
                      },
                    )
                  }
                >
                  <X aria-hidden="true" />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {mutation.isError && (
        <p role="alert" className="text-label text-destructive mt-2">
          {t("today.resume.saveFailed")}
        </p>
      )}
      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("today.resume.clearTitle")}</DialogTitle>
            <DialogDescription>
              {t("today.resume.clearDescription")}
            </DialogDescription>
          </DialogHeader>
          {mutation.isError && (
            <p role="alert" className="text-label text-destructive">
              {t("today.resume.saveFailed")}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setConfirmClear(false)}
            >
              {t("today.resume.cancel")}
            </Button>
            <Button
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate(
                  { action: "clear" },
                  {
                    onSuccess: () => {
                      setConfirmClear(false);
                      requestAnimationFrame(() =>
                        document
                          .getElementById("today-continue-title")
                          ?.focus(),
                      );
                    },
                  },
                )
              }
            >
              {t("today.resume.clear")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
