import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { TodayPlanTask } from "@/features/today/components/TodayPlanTask";
import { TodayPlanItemsDialog } from "@/features/today/components/TodayPlanItemsDialog";
import { useTranslation } from "react-i18next";

import { useCompletePlanItem } from "@/features/learningPlan/api/learningPlan";
import { toastMutationError } from "@/features/learningPlan/components/LearningPlanTab";
import {
  todayApi,
  type TodayPlanItem,
  type TodaySummaryTodo,
} from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";

type TodayTodosProps = {
  summaries: TodaySummaryTodo[] | undefined;
  isSummariesPending: boolean;
  isSummariesError: boolean;
  onRetrySummaries: () => void;
  showSummaries?: boolean;
  course?: string;
  order?: "date" | "duration";
  selectedItemId?: string;
  onFocus: (id: string) => void;
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
  selectedItemId,
  onFocus,
}: TodayTodosProps) {
  const { t } = useTranslation();
  const [allOpen, setAllOpen] = useState(false);
  const moreButton = useRef<HTMLButtonElement>(null);
  const returnToFocus = useRef(false);
  const planItems = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
  });
  const complete = useCompletePlanItem();
  const completeItem = (item: TodayPlanItem) =>
    complete.mutate(
      { courseId: item.course_id, planId: item.plan_id, itemId: item.item_id },
      {
        onError: (error) =>
          toastMutationError(error, t("learningPlan.mutationFailed")),
      },
    );

  if (planItems.isPending && (!showSummaries || isSummariesPending)) {
    return (
      <p role="status" className="text-label text-ink-muted mt-4">
        {t("today.loading")}
      </p>
    );
  }
  if (!allOpen && ((showSummaries && isSummariesError) || planItems.isError)) {
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
  if (!allOpen && !hasPlanItems && !hasSummaries) {
    return null;
  }

  return (
    <div className="min-w-0">
      <h3 className="text-label text-ink-muted sr-only font-medium">
        {t("today.todoTitle")}
      </h3>
      {hasPlanItems ? (
        <div className="today-task-preview">
          <p className="text-label text-ink-faint font-label">
            {t("today.planTodos.groupLabel")}
          </p>
          <ul
            aria-label={t("today.planTodos.listLabel")}
            className="today-task-preview-list"
          >
            {visibleItems.slice(0, 3).map((item) => (
              <li
                key={item.item_id}
                className="min-w-0"
                aria-busy={
                  complete.isPending &&
                  complete.variables?.itemId === item.item_id
                }
              >
                <TodayPlanTask
                  item={item}
                  selected={selectedItemId === item.item_id}
                  busy={
                    complete.isPending &&
                    complete.variables?.itemId === item.item_id
                  }
                  disabled={complete.isPending}
                  onFocus={onFocus}
                  onComplete={completeItem}
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {(hasPlanItems || allOpen) && (
        <Dialog open={allOpen} onOpenChange={setAllOpen}>
          <DialogTrigger
            render={
              <Button
                ref={moreButton}
                variant="secondary"
                size="sm"
                className="today-view-plans"
              />
            }
          >
            {t("today.planDialog.viewMore")}
            <span className="tabular-nums">{visibleItems.length}</span>
            <ArrowRight aria-hidden="true" />
          </DialogTrigger>
          <TodayPlanItemsDialog
            items={visibleItems}
            allItems={planItems.data ?? []}
            selectedItemId={selectedItemId}
            busyItemId={
              complete.isPending ? complete.variables?.itemId : undefined
            }
            isCompleting={complete.isPending}
            error={planItems.isError}
            onRetry={() => void planItems.refetch()}
            onComplete={completeItem}
            onFocus={(id) => {
              returnToFocus.current = true;
              setAllOpen(false);
              onFocus(id);
            }}
            finalFocus={() => {
              const target = returnToFocus.current
                ? document.getElementById("today-focus-title")
                : (moreButton.current ??
                  document.getElementById("today-actions-title"));
              returnToFocus.current = false;
              return target;
            }}
          />
        </Dialog>
      )}
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
