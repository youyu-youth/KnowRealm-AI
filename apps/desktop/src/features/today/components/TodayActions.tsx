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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { todayApi, type TodaySummaryTodo } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { TodayProgressSummary } from "@/features/today/components/TodayProgressSummary";
import { TodayCompletedTasks } from "@/features/today/components/TodayCompletedTasks";
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
  const dateSortLabel = t(
    status === "done"
      ? "today.progress.sortCompleted"
      : "today.workspace.sortDate",
  );
  return (
    <section
      aria-labelledby="today-actions-title"
      className="today-panel today-actions"
    >
      <h2 id="today-actions-title" className="today-heading shrink-0 px-4 pt-4">
        {t("today.workspace.actions")}
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
      <Tabs
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
        className="today-actions-tabs mt-2 gap-0"
      >
        <div className="today-actions-toolbar border-border-subtle flex flex-wrap items-center justify-between gap-2 border-b px-3 pb-2">
          <TabsList variant="line" className="h-auto p-0">
            <TabsTrigger
              value="pending"
              className="data-active:text-today-accent data-active:after:bg-today-accent px-3 py-2"
            >
              {t("today.workspace.toDo")}{" "}
              <span className="ml-1 tabular-nums">
                {data?.pending_count ?? "—"}
              </span>
            </TabsTrigger>
            <TabsTrigger value="done" className="px-3 py-2">
              {t("today.progress.completed")}{" "}
              <span className="ml-1 tabular-nums">
                {data?.completed_count ?? "—"}
              </span>
            </TabsTrigger>
          </TabsList>
          <div className="flex flex-wrap gap-2">
            <Select
              value={course}
              onValueChange={(value) =>
                void navigate({
                  search: (previous) => ({
                    ...previous,
                    course: value ?? "all",
                    completed_page: 1,
                  }),
                  replace: true,
                })
              }
            >
              <SelectTrigger
                size="sm"
                aria-label={t("today.workspace.courseFilter")}
                className="text-label max-w-40"
              >
                <SelectValue>
                  {course === "all"
                    ? t("today.workspace.allCourses")
                    : (courses.find((item) => item.course_id === course)
                        ?.course_name ?? t("today.progress.selectedCourse"))}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  {t("today.workspace.allCourses")}
                </SelectItem>
                {courses.map((item) => (
                  <SelectItem key={item.course_id} value={item.course_id}>
                    {item.course_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={order}
              onValueChange={(value) =>
                void navigate({
                  search: (previous) => ({
                    ...previous,
                    order: value === "duration" ? "duration" : "date",
                    completed_page: 1,
                  }),
                  replace: true,
                })
              }
            >
              <SelectTrigger
                size="sm"
                aria-label={t("today.workspace.sort")}
                className="text-label"
              >
                <SelectValue>
                  {order === "duration"
                    ? t("today.workspace.sortDuration")
                    : dateSortLabel}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="date">{dateSortLabel}</SelectItem>
                <SelectItem value="duration">
                  {t("today.workspace.sortDuration")}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <TabsContent
          value="pending"
          className="today-action-list m-0"
          tabIndex={0}
        >
          <div
            aria-hidden="true"
            className="today-task-row today-task-header bg-today-soft text-label text-ink-muted px-3 py-2"
          >
            <span />
            <span>{t("today.workspace.task")}</span>
            <span>{t("today.workspace.courseColumn")}</span>
            <span>{t("today.workspace.durationColumn")}</span>
            <span>{t("today.workspace.statusColumn")}</span>
            <span />
          </div>
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
            <p className="text-label text-ink-muted p-5">
              {t("today.workspace.noTasks")}
            </p>
          ) : null}
        </TabsContent>
        <TabsContent
          value="done"
          className="today-action-list m-0 p-4"
          tabIndex={0}
          aria-busy={progress.isFetching}
        >
          {progress.isPlaceholderData ? (
            <p role="status" className="text-label text-ink-muted">
              {t("today.loading")}
            </p>
          ) : null}
          {data ? <TodayCompletedTasks progress={data} page={page} /> : null}
        </TabsContent>
      </Tabs>
    </section>
  );
}
