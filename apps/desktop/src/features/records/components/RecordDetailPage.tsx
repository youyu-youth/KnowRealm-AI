import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordOut } from "@/features/records/api/types";
import { DeleteRecordDialog } from "@/features/records/components/DeleteRecordDialog";
import { KnowledgePointPanel } from "@/features/records/components/KnowledgePointPanel";
import {
  RecordExportMenu,
  RecordExportStatus,
} from "@/features/records/components/RecordExportMenu";
import { QuizPanel } from "@/features/records/components/QuizPanel";
import { SummaryPanel } from "@/features/records/components/SummaryPanel";
import { TodoPanel } from "@/features/records/components/TodoPanel";
import { TranscriptPanel } from "@/features/records/components/TranscriptPanel";
import { useRecordExport } from "@/features/records/export/useRecordExport";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { ApiError } from "@/services/http/client";

export type RecordDetailTab =
  "summary" | "transcript" | "knowledge-points" | "quiz" | "todo";

type RecordDetailPageProps = {
  recordId: string;
  tab: RecordDetailTab;
  /** 引用跳转带来的转写定位摘录；在转写中找不到时提示“原文已变动”。 */
  highlight?: string;
  onTabChange: (tab: RecordDetailTab) => void;
  onDeleted: (courseId: string | null) => void | Promise<void>;
};

const unavailableTabs = [
  { value: "review", labelKey: "record.detail.tabs.review" },
  { value: "ask-ai", labelKey: "record.detail.tabs.askAi" },
] as const;

const processingStatuses = new Set([
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export function RecordDetailPage({
  recordId,
  tab,
  highlight,
  onTabChange,
  onDeleted,
}: RecordDetailPageProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [isDeleting, setIsDeleting] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const recordExport = useRecordExport();
  const record = useQuery({
    queryKey: recordKeys.detail(recordId),
    queryFn: () => recordApi.get(recordId),
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404
        ? false
        : failureCount < 2,
  });
  const isProcessing = processingStatuses.has(record.data?.status ?? "");

  const invalidateRecord = useCallback(
    async (includeSummary = true) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: recordKeys.detail(recordId),
        }),
        queryClient.invalidateQueries({ queryKey: recordKeys.jobs(recordId) }),
        ...(includeSummary
          ? [
              queryClient.invalidateQueries({
                queryKey: recordKeys.summary(recordId),
              }),
            ]
          : []),
        queryClient.invalidateQueries({
          queryKey: recordKeys.knowledgePoints(recordId),
        }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.quizzes(recordId),
        }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.todos(recordId),
        }),
        queryClient.invalidateQueries({
          queryKey: recordKeys.transcript(recordId),
        }),
      ]);
    },
    [queryClient, recordId],
  );
  const invalidateSummaryDependents = useCallback(
    () => invalidateRecord(false),
    [invalidateRecord],
  );

  useEffect(() => {
    if (!isProcessing || isDeleting) return;
    let active = true;
    let controller: AbortController | undefined;
    const connect = async () => {
      while (active) {
        controller = new AbortController();
        try {
          await recordApi.subscribe(
            recordId,
            controller.signal,
            () => {
              setStreamConnected(true);
              void invalidateRecord();
            },
            () => void invalidateRecord(),
          );
        } catch {
          if (!active) return;
        }
        setStreamConnected(false);
        await invalidateRecord();
        await new Promise((resolve) => window.setTimeout(resolve, 2_000));
      }
    };
    void connect();
    return () => {
      active = false;
      controller?.abort();
    };
  }, [invalidateRecord, isDeleting, isProcessing, recordId]);

  useEffect(() => {
    if (!isProcessing || streamConnected || isDeleting) return;
    void invalidateRecord();
    const timer = window.setInterval(() => void invalidateRecord(), 2_000);
    return () => window.clearInterval(timer);
  }, [invalidateRecord, isDeleting, isProcessing, streamConnected]);

  useEffect(() => {
    const refresh = () => void invalidateRecord();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [invalidateRecord]);

  if (record.isPending) return <RecordLoading />;
  if (record.isError) {
    const notFound =
      record.error instanceof ApiError && record.error.status === 404;
    return (
      <RecordError notFound={notFound} retry={() => void record.refetch()} />
    );
  }

  const detail = record.data;
  const title = detail.title.trim() || t("spaces.records.untitled");
  const backLinkClass =
    "text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex items-center gap-1.5 rounded-sm transition-colors focus-visible:ring-3";

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full min-w-0 flex-col py-8">
      {detail.course_id ? (
        <Link
          to="/spaces/$courseId"
          params={{ courseId: detail.course_id }}
          search={{ tab: "records" }}
          className={backLinkClass}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t("record.detail.backToCourseRecords")}
        </Link>
      ) : (
        <Link to="/inbox" className={backLinkClass}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t("record.detail.backToInbox")}
        </Link>
      )}

      <header className="mt-5 flex min-w-0 items-baseline justify-between gap-4">
        <h1
          className="text-headline font-headline text-ink-strong min-w-0 truncate"
          title={title}
        >
          {title}
        </h1>
        <div className="flex shrink-0 items-center gap-2">
          <RecordExportMenu
            recordId={recordId}
            tab={tab}
            busy={recordExport.state.phase === "exporting"}
            onExportAll={() => void recordExport.exportAll(recordId, title)}
            onExport={(asset) =>
              void recordExport.exportAsset(asset, recordId, title)
            }
          />
          <DeleteRecordDialog
            recordId={detail.id}
            courseId={detail.course_id}
            title={title}
            onDeletingChange={setIsDeleting}
            onDeleted={onDeleted}
          />
        </div>
      </header>
      <RecordMetadata detail={detail} />
      <RecordExportStatus
        state={recordExport.state}
        onOpenFile={(path) => void recordExport.openSavedFile(path)}
      />

      <Tabs
        value={tab}
        onValueChange={(value) => {
          if (
            value === "summary" ||
            value === "transcript" ||
            value === "knowledge-points" ||
            value === "quiz" ||
            value === "todo"
          ) {
            onTabChange(value);
          }
        }}
        className="mt-8 min-w-0"
      >
        <TabsList
          variant="line"
          className="max-w-full flex-wrap justify-start gap-x-3 gap-y-2"
        >
          <TabsTrigger value="summary">
            {t("record.detail.tabs.summary")}
          </TabsTrigger>
          <TabsTrigger value="transcript">
            {t("record.detail.tabs.transcript")}
          </TabsTrigger>
          <TabsTrigger value="knowledge-points">
            {t("record.detail.tabs.knowledgePoints")}
          </TabsTrigger>
          <TabsTrigger
            value="quiz"
            disabled={detail.status !== "COMPLETED"}
            aria-describedby={
              detail.status === "COMPLETED"
                ? undefined
                : "record-assets-unavailable"
            }
          >
            {t("record.detail.tabs.quiz")}
          </TabsTrigger>
          <TabsTrigger
            value="todo"
            disabled={detail.status !== "COMPLETED"}
            aria-describedby={
              detail.status === "COMPLETED"
                ? undefined
                : "record-assets-unavailable"
            }
          >
            {t("record.detail.tabs.todo")}
          </TabsTrigger>
          {unavailableTabs.map(({ value, labelKey }) => (
            <TabsTrigger
              key={value}
              value={value}
              disabled
              aria-describedby="record-assets-unavailable"
              className="aria-disabled:hover:text-foreground/60 aria-disabled:pointer-events-auto"
            >
              {t(labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        <p
          id="record-assets-unavailable"
          className="text-label text-muted-foreground mt-3"
        >
          {t(
            detail.status === "COMPLETED"
              ? "record.detail.assetsCompleted"
              : "record.detail.assetsUnavailable",
          )}
        </p>

        <TabsContent
          value="summary"
          className="border-border mt-6 border-t pt-8"
        >
          <SummaryPanel
            record={detail}
            onRecordAssetsChanged={invalidateSummaryDependents}
          />
        </TabsContent>

        <TabsContent
          value="transcript"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
          <TranscriptPanel
            record={detail}
            highlight={tab === "transcript" ? highlight : undefined}
            enabled={tab === "transcript" && !isDeleting}
            onRecordAssetsChanged={invalidateRecord}
          />
        </TabsContent>

        <TabsContent
          value="knowledge-points"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
          <KnowledgePointPanel
            recordId={recordId}
            onOpenSummary={() => onTabChange("summary")}
          />
        </TabsContent>

        <TabsContent
          value="quiz"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
          <QuizPanel
            recordId={recordId}
            onOpenSummary={() => onTabChange("summary")}
          />
        </TabsContent>

        <TabsContent
          value="todo"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
          <TodoPanel
            recordId={recordId}
            onOpenSummary={() => onTabChange("summary")}
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}

function RecordLoading() {
  const { t } = useTranslation();
  return (
    <section className="max-w-workbench px-content mx-auto py-8">
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("record.detail.loading")}
      </p>
    </section>
  );
}

function RecordError({
  notFound,
  retry,
}: {
  notFound: boolean;
  retry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <section
      role="alert"
      className="work-surface-enter max-w-workbench px-content mx-auto flex min-h-full flex-col items-start py-8"
    >
      <h1 className="text-headline font-headline text-ink-strong">
        {t(
          notFound ? "record.detail.notFoundTitle" : "record.detail.errorTitle",
        )}
      </h1>
      <p className="max-w-reading text-body text-muted-foreground mt-2">
        {t(
          notFound
            ? "record.detail.notFoundDescription"
            : "record.detail.errorDescription",
        )}
      </p>
      {notFound ? (
        <Link
          to="/spaces"
          className={buttonVariants({ variant: "outline", className: "mt-8" })}
        >
          {t("record.detail.backToSpaces")}
        </Link>
      ) : (
        <Button variant="outline" className="mt-8" onClick={retry}>
          {t("record.detail.retry")}
        </Button>
      )}
    </section>
  );
}

function RecordMetadata({ detail }: { detail: RecordOut }) {
  const { t } = useTranslation();
  return (
    <div className="text-label text-muted-foreground mt-3 flex flex-wrap items-center gap-x-2 gap-y-2">
      <span>{t(captureTypeLabelKeys[detail.capture_type])}</span>
      <span aria-hidden="true">·</span>
      <time dateTime={detail.created_at}>
        {t("spaces.records.createdAt", {
          date: recordDateFormatter.format(new Date(detail.created_at)),
        })}
      </time>
      {detail.duration_ms > 0 ? (
        <>
          <span aria-hidden="true">·</span>
          <span>{formatRecordDuration(detail.duration_ms, t)}</span>
        </>
      ) : null}
      <span
        className={`${statusClassNames[detail.status]} font-label rounded-xs px-2 py-1 whitespace-nowrap`}
      >
        {t(statusLabelKeys[detail.status])}
      </span>
    </div>
  );
}
