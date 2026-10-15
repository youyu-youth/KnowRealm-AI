import { Link, useNavigate } from "@tanstack/react-router";
import { Check } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import type { TodayProgress } from "@/features/today/api/today";

export function TodayCompletedTasks({
  progress,
  page,
}: {
  progress: TodayProgress;
  page: number;
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate({ from: "/" });
  const pages = Math.max(1, Math.ceil(progress.completed_count / 20));
  const previousButton = useRef<HTMLButtonElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const focusDirection = useRef<"previous" | "next" | null>(null);
  const changePage = (next: number) => {
    focusDirection.current = next > page ? "next" : "previous";
    void navigate({
      search: (previous) => ({ ...previous, completed_page: next }),
      replace: true,
    });
  };
  useEffect(() => {
    if (focusDirection.current == null || progress.offset !== (page - 1) * 20)
      return;
    const preferNext =
      focusDirection.current === "next" ? page < pages : page <= 1;
    const target = preferNext ? nextButton.current : previousButton.current;
    if (target && !target.disabled) target.focus();
    else document.getElementById("today-completed-list")?.focus();
    focusDirection.current = null;
  }, [page, pages, progress.offset]);
  return (
    <>
      {progress.completed_count === 0 ? (
        <p
          id="today-completed-list"
          tabIndex={-1}
          className="text-label text-ink-muted"
        >
          {t("today.progress.emptyCompleted")}
        </p>
      ) : (
        <ul
          id="today-completed-list"
          tabIndex={-1}
          aria-label={t("today.progress.completedList")}
          className="divide-border-subtle divide-y"
        >
          {progress.completed_items.map((item) => (
            <li
              key={item.item_id}
              className="flex min-w-0 flex-wrap items-start gap-3 py-3"
            >
              <Check
                className="text-ink-muted mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="text-body font-medium break-words">
                  {item.content}
                </p>
                <p className="text-label text-ink-muted mt-1 break-words">
                  {item.course_name} · {item.goal_title} ·{" "}
                  {t("today.progress.version", { version: item.plan_version })}
                </p>
                <p className="text-label text-ink-muted mt-1">
                  {t("today.progress.completedAt", {
                    time: new Intl.DateTimeFormat(i18n.resolvedLanguage, {
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(item.completed_at)),
                  })}
                  {" · "}
                  {item.estimated_minutes == null
                    ? t("today.progress.unestimated")
                    : t("today.progress.estimated", {
                        minutes: item.estimated_minutes,
                      })}
                </p>
              </div>
              <Link
                to="/spaces/$courseId"
                params={{ courseId: item.course_id }}
                search={{ tab: "plan" }}
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                {t("today.workspace.openPlan")}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {pages > 1 ? (
        <nav
          aria-label={t("today.progress.pagination")}
          className="mt-3 flex flex-wrap items-center justify-end gap-2"
        >
          <Button
            ref={previousButton}
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => changePage(page - 1)}
          >
            {t("today.progress.previous")}
          </Button>
          <span className="text-label text-ink-muted tabular-nums">
            {t("today.progress.page", { page, pages })}
          </span>
          <Button
            ref={nextButton}
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => changePage(page + 1)}
          >
            {t("today.progress.next")}
          </Button>
        </nav>
      ) : null}
    </>
  );
}
