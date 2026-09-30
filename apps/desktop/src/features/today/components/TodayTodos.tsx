import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { Checkbox } from "@/components/ui/checkbox";
import { useCompletePlanItem } from "@/features/learningPlan/api/learningPlan";
import { toastMutationError } from "@/features/learningPlan/components/LearningPlanTab";
import { todayApi, type TodaySummaryTodo } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";

type TodayTodosProps = {
  summaries: TodaySummaryTodo[] | undefined;
  isSummariesPending: boolean;
  isSummariesError: boolean;
  onRetrySummaries: () => void;
};

/** 今日待学双源清单（工单 04）：跨空间学习计划项（排期日 ≤ 今天且未完成，
 * 勾选完成直接作用于计划项）与记录待办（待确认总结）并列分组、标注来源。
 * 计划项与记录待办都为空时整块不出现（沿今日页既有行为）。
 * 样式执行卡内零 chrome（DESIGN.md §148，TodaySummaryTodos 先例）。 */
export function TodayTodos({
  summaries,
  isSummariesPending,
  isSummariesError,
  onRetrySummaries,
}: TodayTodosProps) {
  const { t, i18n } = useTranslation();
  const planItems = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
  });
  const complete = useCompletePlanItem();

  if (isSummariesPending && planItems.isPending) {
    return (
      <p role="status" className="text-label text-ink-muted mt-4">
        {t("today.loading")}
      </p>
    );
  }
  if (isSummariesError || planItems.isError) {
    return (
      <div role="alert" className="border-border-subtle mt-4 border-t pt-4">
        <h3 className="text-body-dense text-destructive font-medium">
          {t("today.errorTitle")}
        </h3>
        <p className="text-label text-ink-muted mt-1">
          {t("today.errorDescription")}
          <button
            type="button"
            className="text-ink ml-2 underline-offset-2 hover:underline"
            onClick={() => {
              onRetrySummaries();
              void planItems.refetch();
            }}
          >
            {t("today.retry")}
          </button>
        </p>
      </div>
    );
  }

  const hasPlanItems = (planItems.data?.length ?? 0) > 0;
  const hasSummaries = (summaries?.length ?? 0) > 0;
  if (!hasPlanItems && !hasSummaries) {
    return null;
  }

  return (
    <div className="border-border/60 mb-4 border-b pb-4">
      <h3 className="text-label text-ink-muted font-medium">
        {t("today.todoTitle")}
      </h3>
      {hasPlanItems ? (
        <div className="mt-2">
          <p className="text-label text-ink-faint font-label">
            {t("today.planTodos.groupLabel")}
          </p>
          <ul
            aria-label={t("today.planTodos.listLabel")}
            className="mt-1.5 grid"
          >
            {planItems.data?.map((item) => (
              <li key={item.item_id} className="min-w-0">
                <div className="hover:bg-surface-subtle -mx-2 flex items-start gap-3 rounded-sm px-2 py-2 transition-colors">
                  <Checkbox
                    aria-label={t("today.planTodos.completeLabel", {
                      content: item.content,
                    })}
                    disabled={
                      complete.isPending &&
                      complete.variables?.itemId === item.item_id
                    }
                    onCheckedChange={() =>
                      complete.mutate(
                        {
                          courseId: item.course_id,
                          planId: item.plan_id,
                          itemId: item.item_id,
                        },
                        {
                          onError: (error) =>
                            toastMutationError(
                              error,
                              t("learningPlan.mutationFailed"),
                            ),
                        },
                      )
                    }
                    className="mt-1"
                  />
                  <div className="min-w-0 flex-1">
                    <Link
                      to="/spaces/$courseId"
                      params={{ courseId: item.course_id }}
                      search={{ tab: "plan" }}
                      className="hover:text-ink-strong block truncate font-medium transition-colors"
                      title={item.content}
                    >
                      {item.content}
                    </Link>
                    <p className="text-label text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="truncate">{item.course_name}</span>
                      {item.estimated_minutes != null ? (
                        <span>
                          {t("today.planTodos.minutes", {
                            minutes: item.estimated_minutes,
                          })}
                        </span>
                      ) : null}
                      <span
                        className="inline-flex items-center gap-0.5"
                        title={t("today.planTodos.scheduledTitle")}
                      >
                        <CalendarClock aria-hidden="true" className="size-3" />
                        {formatDueLabel(
                          item.scheduled_date,
                          i18n.resolvedLanguage,
                          t,
                        )}
                      </span>
                      {isOverdue(item.scheduled_date) ? (
                        <StatusTag tone="warning">
                          {t("today.planTodos.overdue")}
                        </StatusTag>
                      ) : null}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {hasSummaries ? (
        <div className={hasPlanItems ? "mt-3" : "mt-2"}>
          <p className="text-label text-ink-faint font-label">
            {t("today.planTodos.recordGroupLabel")}
          </p>
          <ul aria-label={t("today.todoListLabel")} className="mt-1.5 grid">
            {summaries?.map((todo) => (
              <li key={todo.record_id} className="min-w-0">
                <Link
                  to="/records/$recordId"
                  params={{ recordId: todo.record_id }}
                  className="hover:bg-surface-subtle focus-visible:ring-ring/40 group -mx-2 flex items-center justify-between gap-3 rounded-sm px-2 py-2 transition-colors focus-visible:ring-3"
                >
                  <span className="min-w-0">
                    <span
                      className="text-body text-ink block truncate font-medium"
                      title={todo.title}
                    >
                      {todo.title}
                    </span>
                    <span className="text-label text-muted-foreground mt-0.5 block truncate">
                      {todo.course_name}
                    </span>
                  </span>
                  <span className="text-label text-muted-foreground group-hover:text-ink inline-flex items-center gap-1 whitespace-nowrap transition-colors">
                    {t("today.todoAction")}
                    <ArrowRight
                      aria-hidden="true"
                      className="size-3.5 transition-transform group-hover:translate-x-0.5"
                    />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

// 排期日是按日字符串：与「今日零点」直接比 Date 即得两档判断（逾期 / 即今天）。
function startOfDay(value: Date): number {
  return new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate(),
  ).getTime();
}

function isOverdue(scheduledDate: string): boolean {
  return (
    startOfDay(new Date(`${scheduledDate}T00:00:00`)) < startOfDay(new Date())
  );
}

// 排期日即今天显示「今天」，早于今天显示月日（逾期徽章另标）。
function formatDueLabel(
  scheduledDate: string,
  language: string | undefined,
  t: (key: string) => string,
): string {
  const due = new Date(`${scheduledDate}T00:00:00`);
  if (startOfDay(due) === startOfDay(new Date())) {
    return t("today.planTodos.today");
  }
  return new Intl.DateTimeFormat(language, {
    month: "short",
    day: "numeric",
  }).format(due);
}
