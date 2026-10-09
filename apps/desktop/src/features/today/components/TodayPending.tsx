import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AudioLines, ArrowUpRight, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { recordApi } from "@/features/records/api/records";
import { recordKeys } from "@/features/records/api/keys";
import {
  captureTypeLabelKeys,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { todayKeys } from "@/features/today/api/keys";
import type { TodaySummaryTodo } from "@/features/today/api/today";
import { cn } from "@/lib/utils";

type Props = {
  summaries: TodaySummaryTodo[];
  pending: boolean;
  error: boolean;
  onRetry: () => void;
  selectedId?: string;
  onSelect: (id: string) => void;
};

const processingStatuses = new Set([
  "DRAFT",
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export function TodayPending({
  summaries,
  pending,
  error,
  onRetry,
  selectedId,
  onSelect,
}: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("all");
  const queryClient = useQueryClient();
  const inbox = useQuery({
    queryKey: recordKeys.inbox(),
    queryFn: recordApi.listInbox,
    refetchInterval: (query) =>
      query.state.data?.some((record) => processingStatuses.has(record.status))
        ? 2_000
        : false,
  });
  const records = (inbox.data ?? []).filter(
    (record) =>
      record.status !== "COMPLETED" &&
      !summaries.some((summary) => summary.record_id === record.id),
  );
  const processing = records.filter((record) =>
    processingStatuses.has(record.status),
  );
  const missingSummary = (inbox.data ?? []).some(
    (record) =>
      record.status === "SUMMARY_READY" &&
      record.course_id &&
      !summaries.some((summary) => summary.record_id === record.id),
  );
  useEffect(() => {
    if (missingSummary)
      void queryClient.invalidateQueries({
        queryKey: todayKeys.pendingSummaries,
      });
  }, [missingSummary, queryClient]);
  const sample =
    !pending &&
    !error &&
    !inbox.isPending &&
    !inbox.isError &&
    summaries.length === 0 &&
    records.length === 0;
  const count = summaries.length + records.length;

  return (
    <section aria-labelledby="today-pending-title" className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="today-pending-title" className="today-heading">
          {t("today.workspace.pending")}
        </h2>
        <div className="flex items-center gap-2">
          {sample ? (
            <StatusTag>{t("today.stats.insights.sampleTag")}</StatusTag>
          ) : (
            <StatusTag>{count}</StatusTag>
          )}
          <Link
            to="/inbox"
            className="text-label text-today-accent hover:underline"
          >
            {t("today.overview.openInbox")}
          </Link>
        </div>
      </div>
      <Tabs
        value={filter}
        onValueChange={(value) => setFilter(String(value))}
        className="mt-3"
      >
        <TabsList className="flex-wrap justify-start gap-1 bg-transparent p-0 group-data-horizontal/tabs:h-auto">
          {[
            ["all", "all", count],
            ["summary", "awaiting", summaries.length],
            ["processing", "processing", processing.length],
          ].map(([value, key, total]) => (
            <TabsTrigger
              key={value}
              value={value}
              className="bg-today-soft data-active:bg-today-primary data-active:text-today-primary-foreground dark:data-active:bg-today-primary dark:data-active:text-today-primary-foreground text-label px-3 py-1.5"
            >
              {t(`today.workspace.${key}`)}{" "}
              <span className="ml-1 tabular-nums">
                {sample ? (value === "all" ? 3 : 1) : total}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={filter} className="m-0">
          {pending || inbox.isPending ? (
            <p role="status" className="text-label text-ink-muted py-5">
              {t("today.loading")}
            </p>
          ) : null}
          {error || inbox.isError ? (
            <div role="alert" className="text-label text-destructive mt-3">
              <h3>{t("today.errorTitle")}</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onRetry();
                  void inbox.refetch();
                }}
              >
                {t("today.retry")}
              </Button>
            </div>
          ) : null}
          <div
            tabIndex={0}
            role="region"
            aria-label={t("today.workspace.pendingList")}
            className="mt-3 max-h-80 overflow-y-auto"
          >
            <ul aria-label={t("today.todoListLabel")} className="grid gap-2">
              {filter !== "processing"
                ? summaries.map((summary) => (
                    <li
                      key={summary.record_id}
                      className={cn(
                        "rounded-sm border p-3 transition-colors",
                        selectedId === summary.record_id
                          ? "border-today-accent bg-today-soft"
                          : "hover:bg-today-soft border-transparent",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <FileText
                          className="mt-0.5 size-5 shrink-0"
                          aria-hidden="true"
                        />
                        <div className="min-w-0 flex-1">
                          <Button
                            variant="ghost"
                            onClick={() => onSelect(summary.record_id)}
                            aria-pressed={selectedId === summary.record_id}
                            className="h-auto max-w-full justify-start p-0 text-left whitespace-normal"
                          >
                            <span
                              className="line-clamp-2 break-words"
                              title={summary.title}
                            >
                              {summary.title}
                            </span>
                          </Button>
                          <p className="text-label text-ink-muted mt-1 break-words">
                            {summary.course_name}
                          </p>
                          <StatusTag tone="warning" className="mt-2">
                            {t("today.workspace.awaiting")}
                          </StatusTag>
                        </div>
                        <Link
                          to="/records/$recordId"
                          params={{ recordId: summary.record_id }}
                          aria-label={t("today.workspace.openRecord", {
                            title: summary.title,
                          })}
                          className="text-ink-muted hover:text-today-accent p-1"
                        >
                          <ArrowUpRight className="size-4" aria-hidden="true" />
                        </Link>
                      </div>
                    </li>
                  ))
                : null}
            </ul>
            <ul className="divide-border-subtle divide-y">
              {(filter === "summary"
                ? []
                : filter === "processing"
                  ? processing
                  : records
              ).map((record) => (
                <li key={record.id}>
                  <Link
                    to="/records/$recordId"
                    params={{ recordId: record.id }}
                    className="hover:bg-today-soft flex items-start gap-3 rounded-sm px-3 py-4 transition-colors"
                  >
                    <AudioLines
                      className="mt-0.5 size-5 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium break-words">
                        {record.title}
                      </span>
                      <span className="text-label text-ink-muted mt-1 block">
                        {t(captureTypeLabelKeys[record.capture_type])}
                      </span>
                    </span>
                    <StatusTag
                      tone={record.status === "FAILED" ? "danger" : "neutral"}
                    >
                      {t(statusLabelKeys[record.status])}
                    </StatusTag>
                  </Link>
                </li>
              ))}
              {sample
                ? ["processing", "review", "classify"]
                    .filter(
                      (key) =>
                        filter === "all" ||
                        (filter === "processing"
                          ? key === "processing"
                          : key === "review"),
                    )
                    .map((key) => (
                      <li
                        key={key}
                        className="flex items-start gap-3 px-3 py-4"
                      >
                        {key === "processing" ? (
                          <AudioLines
                            className="mt-0.5 size-5 shrink-0"
                            aria-hidden="true"
                          />
                        ) : (
                          <FileText
                            className="mt-0.5 size-5 shrink-0"
                            aria-hidden="true"
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-body font-medium">
                            {t(`today.overview.actions.${key}.title`)}
                          </p>
                          <p className="text-label text-ink-muted mt-1">
                            {t(`today.overview.actions.${key}.detail`)}
                          </p>
                          <StatusTag className="mt-2">
                            {t(`today.overview.actions.${key}.status`)}
                          </StatusTag>
                        </div>
                      </li>
                    ))
                : null}
            </ul>
          </div>
          {!pending &&
          !error &&
          !inbox.isPending &&
          !inbox.isError &&
          !sample &&
          (filter === "summary"
            ? summaries.length === 0
            : filter === "processing"
              ? processing.length === 0
              : count === 0) ? (
            <p className="text-label text-ink-muted py-5">
              {t("today.workspace.filterEmpty")}
            </p>
          ) : null}
        </TabsContent>
      </Tabs>
    </section>
  );
}
