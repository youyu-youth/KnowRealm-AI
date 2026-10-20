import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { todayApi, type TodaySummaryTodo } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { TodayProgressSummary } from "@/features/today/components/TodayProgressSummary";
import { TodayCompletedTasks } from "@/features/today/components/TodayCompletedTasks";
import { TodayPlanFilters } from "@/features/today/components/TodayPlanFilters";
import { TodayTodos } from "@/features/today/components/TodayTodos";

type Props = {
  summaries: TodaySummaryTodo[] | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  selectedItemId?: string;
  onFocus: (id: string) => void;
};

export function TodayActions({
  summaries,
  loading,
  error,
  onRetry,
  selectedItemId,
  onFocus,
}: Props) {
  const { t } = useTranslation();
  const {
    course = "all",
    order = "date",
    action_status: status = "pending",
    completed_page: page = 1,
  } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const plans = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const progress = useQuery({
    queryKey: todayKeys.progress(course, order, page),
    queryFn: () => todayApi.progress(course, order, page),
    // 翻页保留控件与焦点；换课程时不展示上一课程的汇总。
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[2] === course ? previousData : undefined,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const data = progress.isError ? undefined : progress.data;
  const courses = data?.courses ?? [];
  useEffect(() => {
    if (data && page > Math.max(1, Math.ceil(data.completed_count / 20))) {
      void navigate({
        search: (previous) => ({ ...previous, completed_page: 1 }),
        replace: true,
      });
    }
  }, [data, navigate, page]);
  return (
    <section
      aria-labelledby="today-actions-title"
      className="today-panel today-actions"
    >
      <div className="today-actions-header">
        <h2
          tabIndex={-1}
          id="today-actions-title"
          className="today-heading shrink-0 px-4 pt-4"
        >
          {t("today.redesign.taskTitle")}
        </h2>
        {progress.isError ? (
          <div
            role="alert"
            className="text-label text-destructive shrink-0 px-4 py-2"
          >
            {t("today.progress.error")}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void progress.refetch()}
            >
              {t("today.retry")}
            </Button>
          </div>
        ) : data ? (
          <TodayProgressSummary progress={data} />
        ) : (
          <p role="status" className="text-label text-ink-muted px-4 py-2">
            {t("today.loading")}
          </p>
        )}
      </div>
      <div className="today-actions-body">
        <div className="today-actions-toolbar">
          <Select
            value={status}
            onValueChange={(value) =>
              void navigate({
                search: (previous) => ({
                  ...previous,
                  action_status: value === "done" ? "done" : "pending",
                  completed_page: 1,
                }),
                replace: true,
              })
            }
          >
            <SelectTrigger
              size="sm"
              className="today-actions-status"
              aria-label={t("today.progress.statusFilter")}
            >
              <SelectValue>
                {t(
                  status === "done"
                    ? "today.progress.completedShort"
                    : "today.workspace.toDo",
                )}{" "}
                {status === "done"
                  ? (data?.completed_count ?? "—")
                  : (data?.pending_count ?? "—")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="today-status-options">
              <SelectItem value="pending">
                {t("today.workspace.toDo")} {data?.pending_count ?? "—"}
              </SelectItem>
              <SelectItem value="done">
                {t("today.progress.completedShort")}{" "}
                {data?.completed_count ?? "—"}
              </SelectItem>
            </SelectContent>
          </Select>
          <TodayPlanFilters courses={courses} />
        </div>
        {status === "pending" ? (
          <div className="today-action-list">
            <TodayTodos
              summaries={summaries}
              isSummariesPending={loading}
              isSummariesError={error}
              onRetrySummaries={onRetry}
              showSummaries={false}
              course={course}
              order={order}
              selectedItemId={selectedItemId}
              onFocus={onFocus}
            />
            {!plans.isPending &&
            !plans.isError &&
            !(plans.data ?? []).some(
              (item) => course === "all" || item.course_id === course,
            ) ? (
              <p
                role="status"
                className="today-actions-empty text-label text-ink-muted"
              >
                {t("today.workspace.noTasks")}
              </p>
            ) : null}
          </div>
        ) : (
          <div
            className="today-action-list today-completed-preview"
            aria-busy={progress.isFetching}
          >
            {progress.isPlaceholderData ? (
              <p role="status" className="text-label text-ink-muted">
                {t("today.loading")}
              </p>
            ) : null}
            {data ? (
              <TodayCompletedTasks progress={data} page={page} preview />
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}
