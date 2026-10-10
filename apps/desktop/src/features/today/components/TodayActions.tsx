import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { Checkbox } from "@/components/ui/checkbox";
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
import { TodayTodos } from "@/features/today/components/TodayTodos";

type Props = {
  summaries: TodaySummaryTodo[] | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
};

export function TodayActions({ summaries, loading, error, onRetry }: Props) {
  const { t } = useTranslation();
  const { course = "all", order = "date" } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const [status, setStatus] = useState("pending");
  const plans = useQuery({
    queryKey: todayKeys.planItems,
    queryFn: todayApi.planItems,
  });
  const courses = [
    ...new Map(
      (plans.data ?? []).map((item) => [item.course_id, item.course_name]),
    ).entries(),
  ];
  const sample = !plans.isPending && !plans.isError && plans.data.length === 0;
  const rows = ["scheduling", "docker", "cache", "set"];
  return (
    <section
      aria-labelledby="today-actions-title"
      className="today-panel today-actions overflow-hidden"
    >
      <h2 id="today-actions-title" className="today-heading px-4 pt-4">
        {t("today.workspace.actions")}
      </h2>
      <Tabs
        value={status}
        onValueChange={(value) => setStatus(String(value))}
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
                {sample ? 4 : (plans.data?.length ?? 0)}
              </span>
            </TabsTrigger>
            <TabsTrigger value="done" className="px-3 py-2">
              {t("today.workspace.done")}
              <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
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
                    : (courses.find(([id]) => id === course)?.[1] ??
                      t("today.workspace.allCourses"))}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  {t("today.workspace.allCourses")}
                </SelectItem>
                {courses.map(([id, name]) => (
                  <SelectItem key={id} value={id}>
                    {name}
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
                  {t(
                    `today.workspace.${order === "duration" ? "sortDuration" : "sortDate"}`,
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="date">
                  {t("today.workspace.sortDate")}
                </SelectItem>
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
          </div>
          <TodayTodos
            summaries={summaries}
            isSummariesPending={loading}
            isSummariesError={error}
            onRetrySummaries={onRetry}
            showSummaries={false}
            course={course}
            order={order}
          />
          {sample && course === "all" ? (
            <div>
              <div className="flex items-center gap-2 px-4 pt-3">
                <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
                <span className="text-label text-ink-muted">
                  {t("today.workspace.sampleTasks")}
                </span>
              </div>
              <ul className="divide-border-subtle mt-2 divide-y">
                {rows.map((key, index) => (
                  <li key={key} className="today-task-row px-4 py-3">
                    <Checkbox
                      checked={false}
                      disabled
                      aria-label={t(`today.workspace.tasks.${key}.title`)}
                    />
                    <div className="min-w-0">
                      <p className="text-body font-semibold">
                        {t(`today.workspace.tasks.${key}.title`)}
                      </p>
                      <p className="text-label text-ink-muted mt-0.5">
                        {t(`today.workspace.tasks.${key}.detail`)}
                      </p>
                    </div>
                    <span className="text-label text-ink-muted">
                      {t(`today.workspace.tasks.${key}.course`)}
                    </span>
                    <span className="text-label text-ink-muted">
                      {t("today.planTodos.minutes", {
                        minutes: index % 2 === 0 ? 60 : 45,
                      })}
                      <span className="mt-0.5 block">
                        {t("today.planTodos.today")}
                      </span>
                    </span>
                    <StatusTag tone={index === 1 ? "warning" : "neutral"}>
                      {t(
                        index === 1
                          ? "today.planTodos.overdue"
                          : "today.workspace.notStarted",
                      )}
                    </StatusTag>
                  </li>
                ))}
              </ul>
            </div>
          ) : !plans.isPending &&
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
        >
          <p className="text-label text-ink-muted mb-3">
            {t("today.workspace.completedHint")}
          </p>
          <ul className="divide-border-subtle divide-y">
            {["cache", "set"].map((key) => (
              <li key={key} className="flex items-center gap-3 py-3">
                <Checkbox
                  checked
                  disabled
                  aria-label={t(`today.workspace.tasks.${key}.title`)}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-body font-medium">
                    {t(`today.workspace.tasks.${key}.title`)}
                  </p>
                  <p className="text-label text-ink-muted mt-1">
                    {t(`today.workspace.tasks.${key}.course`)}
                  </p>
                </div>
                <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
              </li>
            ))}
          </ul>
        </TabsContent>
      </Tabs>
    </section>
  );
}
