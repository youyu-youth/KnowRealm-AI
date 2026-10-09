import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusTag } from "@/components/common/StatusTag";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { useCompletePlanItem } from "@/features/learningPlan/api/learningPlan";
import { toastMutationError } from "@/features/learningPlan/components/LearningPlanTab";
import { todayApi, type TodaySummaryTodo } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";

type TodayTodosProps = {
  summaries: TodaySummaryTodo[] | undefined;
  isSummariesPending: boolean;
  isSummariesError: boolean;
  onRetrySummaries: () => void;
  showSummaries?: boolean;
  course?: string;
  order?: "date" | "duration";
};

/** 跨空间待学清单：勾选完成作用于真实计划项；工作台将待确认总结放在左栏。
 * 保留总结分组供原有调用方使用，筛选后无内容时不渲染清单。 */
export function TodayTodos({
  summaries,
  isSummariesPending,
  isSummariesError,
  onRetrySummaries,
  showSummaries = true,
  course = "all",
  order = "date",
}: TodayTodosProps) {
  const { t, i18n } = useTranslation();
  const planItems = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
  });
  const complete = useCompletePlanItem();

  if (planItems.isPending && (!showSummaries || isSummariesPending)) {
    return (
      <p role="status" className="text-label text-ink-muted mt-4">
        {t("today.loading")}
      </p>
    );
  }
  if ((showSummaries && isSummariesError) || planItems.isError) {
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

  const visibleItems = (planItems.data ?? [])
    .filter((item) => course === "all" || item.course_id === course)
    .sort((a, b) =>
      order === "duration"
        ? (b.estimated_minutes ?? 0) - (a.estimated_minutes ?? 0)
        : a.scheduled_date.localeCompare(b.scheduled_date),
    );
  const hasPlanItems = visibleItems.length > 0;
  const hasSummaries = showSummaries && (summaries?.length ?? 0) > 0;
  if (!hasPlanItems && !hasSummaries) {
    return null;
  }

  return (
    <div className="min-w-0">
      <h3 className="text-label text-ink-muted sr-only font-medium">
        {t("today.todoTitle")}
      </h3>
      {hasPlanItems ? (
        <div className="mt-2">
          <p className="text-label text-ink-faint font-label">
            {t("today.planTodos.groupLabel")}
          </p>
          <ul
            aria-label={t("today.planTodos.listLabel")}
            className="divide-border-subtle mt-1.5 grid divide-y"
          >
            {visibleItems.map((item) => (
              <li
                key={item.item_id}
                className="min-w-0"
                aria-busy={
                  complete.isPending &&
                  complete.variables?.itemId === item.item_id
                }
              >
                <div className="today-task-row hover:bg-today-soft px-3 py-2.5 transition-colors">
                  <Checkbox
                    aria-label={t("today.planTodos.completeLabel", {
                      content: item.content,
                    })}
                    // 受控绑定未完成态（计划 Tab checked={done} 同构）：列表项
                    // 本就只含待学项、完成即随缓存失效离开列表，恒 false 让
                    // 失败回执后不可能残留假勾选（非受控点击即翻转，会与
                    // 服务端 PENDING 不一致）。
                    checked={false}
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
                      className="hover:text-today-accent block font-medium transition-colors"
                      title={item.content}
                    >
                      <span className="line-clamp-2 break-words">
                        {item.content}
                      </span>
                    </Link>
                    <p
                      className="text-label text-ink-muted mt-0.5 truncate"
                      title={item.goal_title}
                    >
                      {item.goal_title}
                    </p>
                  </div>
                  <span className="text-label text-ink-muted break-words">
                    {item.course_name}
                  </span>
                  <div className="text-label text-ink-muted">
                    <p className="text-label text-muted-foreground mt-0.5 grid gap-1">
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
                    </p>
                  </div>
                  {complete.isPending &&
                  complete.variables?.itemId === item.item_id ? (
                    <span
                      role="status"
                      className="text-label text-ink-muted flex items-center gap-1"
                    >
                      <Spinner className="size-3" />
                      {t("today.workspace.completing")}
                    </span>
                  ) : (
                    <StatusTag
                      tone={
                        isOverdue(item.scheduled_date) ? "warning" : "neutral"
                      }
                    >
                      {t(
                        isOverdue(item.scheduled_date)
                          ? "today.planTodos.overdue"
                          : "today.workspace.notStarted",
                      )}
                    </StatusTag>
                  )}
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
