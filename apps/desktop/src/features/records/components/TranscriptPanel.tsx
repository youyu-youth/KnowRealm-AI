import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { ProcessingJobOut, RecordOut } from "@/features/records/api/types";
import { settingsApi } from "@/features/settings/api/settings";
import { formatTimelineTimestamp } from "@/features/records/recordPresentation";
import { ApiError } from "@/services/http/client";

type TranscriptPanelProps = {
  record: RecordOut;
  highlight?: string;
  /** 来源锚点分片 id：优先于 highlight 文本精确定位到指定分片。 */
  segmentId?: string;
  enabled: boolean;
  onRecordAssetsChanged: () => void | Promise<void>;
};

const processingStatuses = new Set([
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export function TranscriptPanel({
  record,
  highlight,
  segmentId,
  enabled,
  onRecordAssetsChanged,
}: TranscriptPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [editBaseVersion, setEditBaseVersion] = useState<number | null>(null);
  const recordId = record.id;
  const jobs = useQuery({
    queryKey: recordKeys.jobs(recordId),
    queryFn: () => recordApi.getJobs(recordId),
    enabled,
  });
  const transcript = useQuery({
    queryKey: recordKeys.transcript(recordId),
    queryFn: () => recordApi.getTranscript(recordId),
    enabled,
  });
  const transcriptSegments = useQuery({
    queryKey: recordKeys.transcriptSegments(recordId),
    queryFn: () => recordApi.getTranscriptSegments(recordId),
    enabled: enabled && transcript.data?.status === "READY",
  });
  // 文档导入的分片在 document_segments（块级、导入即有）；行级 transcript_segments
  // 对文档只有启动回填/编辑重切两个来源，作为旧文档（票 03 之前）的回落。
  const isDocumentImport = record.capture_type === "DOCUMENT_IMPORT";
  const documentSegments = useQuery({
    queryKey: recordKeys.documentSegments(recordId),
    queryFn: () => recordApi.getDocumentSegments(recordId),
    enabled: enabled && transcript.data?.status === "READY" && isDocumentImport,
  });
  const retryJob = useMutation({
    mutationFn: (job: ProcessingJobOut) => recordApi.retryJob(job.id, recordId),
    onSuccess: () => void onRecordAssetsChanged(),
  });
  const grantConsent = useMutation({
    mutationFn: settingsApi.grantTencentAsrConsent,
    onSuccess: () => void onRecordAssetsChanged(),
  });
  const saveTranscript = useMutation({
    mutationFn: (expectedSourceVersion: number) =>
      recordApi.updateTranscript(recordId, {
        content: draft,
        expected_source_version: expectedSourceVersion,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(recordKeys.transcript(recordId), {
        status: "READY",
        transcript: updated,
      });
      // 编辑保存后服务端重切了行级分片并清零了失效的文档块，两个分片源都重拉。
      void queryClient.invalidateQueries({
        queryKey: recordKeys.transcriptSegments(recordId),
      });
      void queryClient.invalidateQueries({
        queryKey: recordKeys.documentSegments(recordId),
      });
      setEditing(false);
      setEditBaseVersion(null);
      void onRecordAssetsChanged();
    },
  });
  const failedJob = jobs.data?.jobs.find((job) =>
    ["FAILED", "CANCELLED"].includes(job.status),
  );
  const waitingJob = jobs.data?.jobs.find((job) => job.waiting_reason);
  const readyTranscript =
    transcript.data?.status === "READY" ? transcript.data.transcript : null;
  const conflict =
    saveTranscript.error instanceof ApiError &&
    saveTranscript.error.status === 409;
  const isProcessing = processingStatuses.has(record.status);
  const timelineRows = useMemo<TimelineRow[] | null>(() => {
    // 优先级：文档块（文档记录导入即有、带页码）> 行级转写分片（音频句级 /
    // 旧文档启动回填）> 纯文本回落。
    if (
      documentSegments.data !== undefined &&
      documentSegments.data.length > 0
    ) {
      return documentSegments.data.map((segment) => ({
        id: segment.id,
        marker:
          segment.page_no === null
            ? null
            : t("record.detail.transcript.pageLabel", {
                page: segment.page_no,
              }),
        content: segment.content,
      }));
    }
    if (
      transcriptSegments.data !== undefined &&
      transcriptSegments.data.length > 0
    ) {
      return transcriptSegments.data.map((segment) => ({
        id: segment.id,
        marker:
          segment.record_start_ms === null
            ? null
            : formatTimelineTimestamp(segment.record_start_ms),
        content: segment.content,
      }));
    }
    return null;
  }, [documentSegments.data, transcriptSegments.data, t]);
  const timelinePending =
    transcriptSegments.isPending ||
    (isDocumentImport && documentSegments.isPending);

  async function reloadTranscript() {
    const result = await transcript.refetch();
    if (result.data?.status === "READY" && result.data.transcript) {
      setDraft(result.data.transcript.content);
      setEditBaseVersion(result.data.transcript.source_version);
    }
    // 冲突意味着服务端内容已被换掉，分片随之重切，一并重拉。
    void transcriptSegments.refetch();
    if (isDocumentImport) void documentSegments.refetch();
    saveTranscript.reset();
  }

  return (
    <>
      {jobs.data?.jobs.length ? <JobProgress jobs={jobs.data} /> : null}
      {waitingJob?.waiting_reason ? (
        <WaitingState
          reason={waitingJob.waiting_reason}
          pending={grantConsent.isPending}
          error={grantConsent.error}
          grant={() => grantConsent.mutate()}
        />
      ) : null}
      {failedJob ? (
        <FailedState
          job={failedJob}
          retrying={retryJob.isPending}
          error={retryJob.error}
          retry={() => retryJob.mutate(failedJob)}
        />
      ) : readyTranscript ? (
        <section className="max-w-reading min-w-0">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-section font-section text-ink">
              {t("record.detail.transcript.contentTitle")}
            </h2>
            {!editing ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={record.status === "SUMMARY_PROCESSING"}
                onClick={() => {
                  setDraft(readyTranscript.content);
                  setEditBaseVersion(readyTranscript.source_version);
                  setEditing(true);
                  saveTranscript.reset();
                }}
              >
                <Pencil aria-hidden="true" />
                {t("record.detail.transcript.edit")}
              </Button>
            ) : null}
          </div>
          {editing ? (
            <div className="mt-4">
              <Textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={16}
                aria-label={t("record.detail.transcript.editorLabel")}
              />
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  disabled={
                    !draft.trim() ||
                    editBaseVersion === null ||
                    saveTranscript.isPending
                  }
                  onClick={() => {
                    if (editBaseVersion !== null) {
                      saveTranscript.mutate(editBaseVersion);
                    }
                  }}
                >
                  {saveTranscript.isPending ? (
                    <Spinner aria-hidden="true" />
                  ) : null}
                  {t("record.detail.transcript.save")}
                </Button>
                <Button
                  variant="outline"
                  disabled={saveTranscript.isPending}
                  onClick={() => {
                    setEditing(false);
                    setEditBaseVersion(null);
                    saveTranscript.reset();
                  }}
                >
                  {t("record.detail.transcript.cancelEdit")}
                </Button>
              </div>
              {saveTranscript.isError ? (
                <Alert variant="destructive" className="mt-4">
                  <AlertDescription className="flex flex-col items-start">
                    {conflict
                      ? t("record.detail.transcript.conflict")
                      : saveTranscript.error.message}
                    {conflict ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-3"
                        onClick={() => void reloadTranscript()}
                      >
                        {t("record.detail.transcript.reload")}
                      </Button>
                    ) : null}
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : timelinePending ? (
            <p
              role="status"
              className="text-body text-muted-foreground mt-4 flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {t("record.detail.transcript.segmentsLoading")}
            </p>
          ) : timelineRows !== null ? (
            <SourceTimeline rows={timelineRows} highlight={highlight} segmentId={segmentId} />
          ) : (
            // 无分片记录（粘贴/速记）回落纯文本；分片读取失败时同样回落，正文仍可读。
            <TranscriptView
              content={readyTranscript.content}
              highlight={highlight}
            />
          )}
        </section>
      ) : jobs.isError || transcript.isError ? (
        <section className="max-w-reading">
          <h2 className="text-section font-section text-ink">
            {t("record.detail.transcript.errorTitle")}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {(jobs.error ?? transcript.error)?.message}
          </p>
        </section>
      ) : jobs.isPending || transcript.isPending || isProcessing ? (
        <section className="max-w-reading">
          <h2 className="text-section font-section text-ink flex items-center gap-2">
            <Spinner aria-hidden="true" />
            {t("record.detail.transcript.processingTitle")}
          </h2>
          <p role="status" className="text-body text-muted-foreground mt-2">
            {t("record.detail.transcript.processingDescription")}
          </p>
        </section>
      ) : (
        <section className="max-w-reading">
          <h2 className="text-section font-section text-ink">
            {t("record.detail.transcript.notReadyTitle")}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {t("record.detail.transcript.notReadyDescription")}
          </p>
        </section>
      )}
    </>
  );
}

/** 转写只读视图：带 highlight 时定位首个匹配并滚动高亮；找不到则提示“原文已变动”。 */
function TranscriptView({
  content,
  highlight,
}: {
  content: string;
  highlight?: string;
}) {
  const { t } = useTranslation();
  const markRef = useRef<HTMLElement | null>(null);
  const position = highlight ? content.indexOf(highlight) : -1;

  useEffect(() => {
    if (position >= 0) {
      markRef.current?.scrollIntoView({ block: "center" });
    }
  }, [position, highlight]);

  return (
    <>
      {highlight && position < 0 ? (
        <p role="status" className="text-label text-muted-foreground mt-4">
          {t("record.detail.transcript.highlightMissing")}
        </p>
      ) : null}
      <pre className="text-body text-ink font-body mt-4 min-w-0 font-sans break-words whitespace-pre-wrap">
        {position >= 0 && highlight ? (
          <>
            {content.slice(0, position)}
            <mark
              ref={markRef}
              className="bg-learning-soft text-ink rounded-xs"
              aria-label={t("record.detail.transcript.highlightLabel")}
            >
              {highlight}
            </mark>
            {content.slice(position + highlight.length)}
          </>
        ) : (
          content
        )}
      </pre>
    </>
  );
}

type TimelineRow = {
  id: string;
  /** 左列标记：音频时间戳（mm:ss / h:mm:ss）或 PDF 页码；null = 无标记来源。 */
  marker: string | null;
  content: string;
};

/**
 * 来源时间轴：行式排布（左标记列、右内容）。标记列三态——时间戳 / 页码 /
 * 全表无任何标记时退为淡色块序号（保证时间轴结构可见；序号非时间标记，
 * 不违「无时间轴来源不造时间」语义）。无标记行保留占位列维持文本基线对齐。
 * 定位优先级：来源分片 id（segmentId）精确命中行 → 摘录文本（highlight，
 * 多命中取首个）回落；命中行滚动 + 摘录内联高亮 + 标记升级徽章，都找不到
 * 提示「原文已变动」。
 */
function SourceTimeline({
  rows,
  highlight,
  segmentId,
}: {
  rows: TimelineRow[];
  highlight?: string;
  segmentId?: string;
}) {
  const { t } = useTranslation();
  const matchRowRef = useRef<HTMLLIElement | null>(null);
  const segmentIndex = segmentId ? rows.findIndex((row) => row.id === segmentId) : -1;
  const matchIndex =
    segmentIndex >= 0
      ? segmentIndex
      : highlight
        ? rows.findIndex((row) => row.content.includes(highlight))
        : -1;
  const hasMarkers = rows.some((row) => row.marker !== null);

  useEffect(() => {
    if (matchIndex >= 0) {
      matchRowRef.current?.scrollIntoView({ block: "center" });
    }
  }, [matchIndex]);

  return (
    <>
      {highlight && matchIndex < 0 ? (
        <p role="status" className="text-label text-muted-foreground mt-4">
          {t("record.detail.transcript.highlightMissing")}
        </p>
      ) : null}
      <ul
        aria-label={t("record.detail.transcript.timelineLabel")}
        className="border-border text-body text-ink mt-4 divide-y font-sans"
      >
        {rows.map((row, index) => {
          const matched = index === matchIndex;
          const marker =
            row.marker ??
            (hasMarkers ? null : String(index + 1).padStart(2, "0"));
          const quoteOffset =
            matched && highlight ? row.content.indexOf(highlight) : -1;
          return (
            <li
              key={row.id}
              ref={matched ? matchRowRef : undefined}
              className="flex min-w-0 items-baseline gap-3 py-1.5"
            >
              {marker !== null ? (
                matched ? (
                  <span className="bg-primary text-primary-foreground font-label w-16 shrink-0 rounded-xs py-0.5 text-center whitespace-nowrap tabular-nums">
                    {marker}
                  </span>
                ) : (
                  <span className="text-label text-muted-foreground w-16 shrink-0 whitespace-nowrap tabular-nums">
                    {marker}
                  </span>
                )
              ) : (
                <span className="w-16 shrink-0" aria-hidden="true" />
              )}
              <p className="min-w-0 break-words">
                {quoteOffset >= 0 && highlight ? (
                  <>
                    {row.content.slice(0, quoteOffset)}
                    <mark
                      className="bg-learning-soft text-ink rounded-xs"
                      aria-label={t("record.detail.transcript.highlightLabel")}
                    >
                      {highlight}
                    </mark>
                    {row.content.slice(quoteOffset + highlight.length)}
                  </>
                ) : (
                  row.content
                )}
              </p>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function JobProgress({
  jobs,
}: {
  jobs: Awaited<ReturnType<typeof recordApi.getJobs>>;
}) {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t("record.detail.jobs.title")}
      className="max-w-reading mb-8"
    >
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-section font-section text-ink">
          {t("record.detail.jobs.title")}
        </h2>
        <span className="text-label text-muted-foreground tabular-nums">
          {t("record.detail.jobs.progress", {
            value: Math.round(jobs.progress * 100),
          })}
        </span>
      </div>
      <progress
        className="mt-3 h-1.5 w-full"
        max={1}
        value={jobs.progress}
        aria-label={t("record.detail.jobs.progressLabel")}
      />
      <ul className="border-border mt-3 divide-y">
        {jobs.jobs.map((job) => (
          <li
            key={job.id}
            className="text-body flex min-w-0 items-center justify-between gap-4 py-3"
          >
            <span className="min-w-0 truncate">
              {job.source_name ? `${job.source_name} · ` : null}
              {t(`record.detail.jobs.types.${job.job_type}`)}
            </span>
            <span className="text-label text-muted-foreground shrink-0">
              {t(`record.detail.jobs.status.${job.status}`)}
              {job.attempts > 0 &&
              job.status !== "SUCCEEDED" &&
              job.status !== "CANCELLED"
                ? ` · ${t("record.detail.jobs.attempts", {
                    current: job.attempts,
                    max: job.max_attempts,
                  })}`
                : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function WaitingState({
  reason,
  pending,
  error,
  grant,
}: {
  reason: NonNullable<ProcessingJobOut["waiting_reason"]>;
  pending: boolean;
  error: Error | null;
  grant: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Alert className="max-w-reading mb-8">
      <AlertDescription className="flex flex-col items-start gap-4">
        <span>{t(`record.detail.transcript.waiting.${reason}`)}</span>
        {reason === "CONSENT_REQUIRED" ? (
          <>
            <span>{t("record.detail.transcript.consentDisclosure")}</span>
            <Button variant="outline" disabled={pending} onClick={grant}>
              {pending ? <Spinner aria-hidden="true" /> : null}
              {t("record.detail.transcript.grantConsent")}
            </Button>
          </>
        ) : null}
        {error ? (
          <span role="alert" className="text-destructive">
            {error.message}
          </span>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

function FailedState({
  job,
  retrying,
  error,
  retry,
}: {
  job: ProcessingJobOut;
  retrying: boolean;
  error: Error | null;
  retry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <section className="max-w-reading">
      <h2 className="text-section font-section text-ink">
        {t("record.detail.transcript.errorTitle")}
      </h2>
      <p className="text-body text-muted-foreground mt-2">
        {job.status === "CANCELLED"
          ? t("record.detail.transcript.cancelledDescription")
          : t(
              `record.detail.transcript.errors.${job.error_code ?? "INTERNAL_ERROR"}`,
            )}
      </p>
      {job.status === "FAILED" && job.retryable ? (
        <Button
          variant="outline"
          className="mt-5"
          disabled={retrying}
          onClick={retry}
        >
          {retrying ? <Spinner aria-hidden="true" /> : null}
          {t(
            retrying
              ? "record.detail.transcript.retrying"
              : "record.detail.transcript.retry",
          )}
        </Button>
      ) : null}
      {error ? (
        <p role="alert" className="text-body text-destructive mt-3">
          {error.message}
        </p>
      ) : null}
    </section>
  );
}
