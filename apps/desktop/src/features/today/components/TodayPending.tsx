import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { recordApi } from "@/features/records/api/records";
import { recordKeys } from "@/features/records/api/keys";
import { captureTypeLabelKeys } from "@/features/records/recordPresentation";
import { todayKeys } from "@/features/today/api/keys";
import type { TodaySummaryTodo } from "@/features/today/api/today";
import { TodayPendingRecord } from "@/features/today/components/TodayPendingRecord";

type Props = {
  summaries: TodaySummaryTodo[];
  pending: boolean;
  error: boolean;
  onRetry: () => void;
};
const processingStatuses = new Set([
  "DRAFT",
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export function TodayPending({ summaries, pending, error, onRetry }: Props) {
  const { t } = useTranslation();
  const { pending_filter: filter = "all", pending_page: page = 1 } = useSearch({
    from: "/",
  });
  const navigate = useNavigate({ from: "/" });
  const queryClient = useQueryClient();
  const list = useRef<HTMLUListElement>(null);
  const [pageSize, setPageSize] = useState(2);
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
  useEffect(() => {
    const element = list.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry || entry.contentRect.height <= 0) return;
      const style = getComputedStyle(element);
      const rowHeight = parseFloat(style.gridAutoRows);
      const gap = parseFloat(style.rowGap);
      if (!Number.isFinite(rowHeight) || rowHeight <= 0) return;
      // 按实际行高和间距分页，跟随主题字号与面板高度。
      setPageSize(
        Math.max(
          1,
          Math.min(
            3,
            Math.floor((entry.contentRect.height + gap) / (rowHeight + gap)),
          ),
        ),
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const items = [
    ...(filter === "processing"
      ? []
      : summaries.map((summary) => ({
          id: summary.record_id,
          title: summary.title,
          detail: summary.course_name,
          status: "SUMMARY_READY" as const,
          captureType: undefined,
        }))),
    ...(filter === "summary"
      ? []
      : filter === "processing"
        ? processing
        : records
    ).map((record) => ({
      id: record.id,
      title: record.title,
      detail: t(captureTypeLabelKeys[record.capture_type]),
      status: record.status,
      captureType: record.capture_type,
    })),
  ];
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pages);
  const loading = pending || inbox.isPending;
  const failed = error || inbox.isError;
  useEffect(() => {
    if (!loading && !failed && page > pages)
      void navigate({
        search: (previous) => ({ ...previous, pending_page: pages }),
        replace: true,
        resetScroll: false,
      });
  }, [failed, loading, navigate, page, pages]);
  const changePage = (next: number) =>
    void navigate({
      search: (previous) => ({ ...previous, pending_page: next }),
      resetScroll: false,
      replace: true,
    });
  return (
    <section
      aria-labelledby="today-pending-title"
      className="today-pending p-4"
    >
      <div className="today-pending-header">
        <h2 id="today-pending-title" className="today-heading">
          {t("today.workspace.pending")}
        </h2>
        <div className="flex items-center gap-2">
          <StatusTag>{summaries.length + records.length}</StatusTag>
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
        onValueChange={(value) =>
          void navigate({
            search: (previous) => ({
              ...previous,
              pending_filter:
                value === "summary" || value === "processing" ? value : "all",
              pending_page: 1,
            }),
            resetScroll: false,
            replace: true,
          })
        }
        className="today-pending-tabs"
      >
        <TabsList className="today-pending-filters flex-wrap justify-start gap-1 bg-transparent p-0 group-data-horizontal/tabs:h-auto">
          {[
            ["all", "all", summaries.length + records.length],
            ["summary", "awaiting", summaries.length],
            ["processing", "processing", processing.length],
          ].map(([value, key, total]) => (
            <TabsTrigger
              key={value}
              value={value}
              className="bg-today-soft data-active:bg-today-filter-selected data-active:text-today-primary-foreground dark:data-active:bg-today-filter-selected dark:data-active:text-today-primary-foreground text-label h-7 flex-none gap-1 px-2 py-1.5"
            >
              {t(`today.workspace.${key}`)}
              <span className="tabular-nums">{total}</span>
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={filter} className="today-pending-content m-0">
          {loading ? (
            <p role="status" className="text-label text-ink-muted py-5">
              {t("today.loading")}
            </p>
          ) : null}
          {failed ? (
            <div role="alert" className="text-label text-destructive py-3">
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
          <ul
            ref={list}
            aria-label={t("today.workspace.pendingList")}
            className="today-pending-list"
          >
            {!loading && !failed
              ? items
                  .slice((currentPage - 1) * pageSize, currentPage * pageSize)
                  .map((item) => (
                    <li key={item.id} className="today-pending-item">
                      <TodayPendingRecord item={item} />
                    </li>
                  ))
              : null}
            {!loading && !failed && items.length === 0 ? (
              <li className="today-pending-empty text-label text-ink-muted">
                <Inbox className="size-7" aria-hidden="true" />
                {t("today.workspace.filterEmpty")}
              </li>
            ) : null}
          </ul>
          {!loading && !failed && pages > 1 ? (
            <nav
              aria-label={t("today.workspace.pendingPagination")}
              className="today-pending-pagination"
            >
              <span
                className="text-label text-ink-muted tabular-nums"
                aria-live="polite"
              >
                {t("today.progress.page", { page: currentPage, pages })}
              </span>
              <Button
                size="icon-sm"
                variant="ghost"
                disabled={currentPage <= 1}
                aria-label={t("today.progress.previous")}
                onClick={() => changePage(currentPage - 1)}
              >
                <ChevronLeft aria-hidden="true" />
              </Button>
              <Button
                size="icon-sm"
                variant="ghost"
                disabled={currentPage >= pages}
                aria-label={t("today.progress.next")}
                onClick={() => changePage(currentPage + 1)}
              >
                <ChevronRight aria-hidden="true" />
              </Button>
            </nav>
          ) : null}
        </TabsContent>
      </Tabs>
    </section>
  );
}
