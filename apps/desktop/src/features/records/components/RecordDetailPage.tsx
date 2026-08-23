import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, Pencil } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { ProcessingJobOut, RecordOut } from "@/features/records/api/types";
import { DeleteRecordDialog } from "@/features/records/components/DeleteRecordDialog";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { settingsApi } from "@/features/settings/api/settings";
import { ApiError } from "@/services/http/client";

type RecordDetailPageProps = {
  recordId: string;
  tab: "summary" | "transcript";
  onTabChange: (tab: "summary" | "transcript") => void;
  onDeleted: (courseId: string | null) => void | Promise<void>;
};

const unavailableTabs = [
  { value: "highlights", labelKey: "record.detail.tabs.highlights" },
  { value: "notes", labelKey: "record.detail.tabs.notes" },
  { value: "flashcards", labelKey: "record.detail.tabs.flashcards" },
  { value: "quiz", labelKey: "record.detail.tabs.quiz" },
] as const;

const processingStatuses = new Set([
  "CONTENT_PROCESSING",
  "SUMMARY_PROCESSING",
]);

export function RecordDetailPage({
  recordId,
  tab,
  onTabChange,
  onDeleted,
}: RecordDetailPageProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [isDeleting, setIsDeleting] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [editBaseVersion, setEditBaseVersion] = useState<number | null>(null);
  const record = useQuery({
    queryKey: recordKeys.detail(recordId),
    queryFn: () => recordApi.get(recordId),
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404
        ? false
        : failureCount < 2,
  });
  const jobs = useQuery({
    queryKey: recordKeys.jobs(recordId),
    queryFn: () => recordApi.getJobs(recordId),
    enabled: tab === "transcript" && !isDeleting,
  });
  const transcript = useQuery({
    queryKey: recordKeys.transcript(recordId),
    queryFn: () => recordApi.getTranscript(recordId),
    enabled: tab === "transcript" && !isDeleting,
  });
  const isProcessing = processingStatuses.has(record.data?.status ?? "");

  const invalidateRecord = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: recordKeys.detail(recordId) }),
      queryClient.invalidateQueries({ queryKey: recordKeys.jobs(recordId) }),
      queryClient.invalidateQueries({
        queryKey: recordKeys.transcript(recordId),
      }),
    ]);
  }, [queryClient, recordId]);

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

  const retryJob = useMutation({
    mutationFn: (job: ProcessingJobOut) => recordApi.retryJob(job.id, recordId),
    onSuccess: () => void invalidateRecord(),
  });
  const grantConsent = useMutation({
    mutationFn: settingsApi.grantTencentAsrConsent,
    onSuccess: () => void invalidateRecord(),
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
      setEditing(false);
      setEditBaseVersion(null);
      void invalidateRecord();
    },
  });

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
  const failedJob = jobs.data?.jobs.find((job) =>
    ["FAILED", "CANCELLED"].includes(job.status),
  );
  const waitingJob = jobs.data?.jobs.find((job) => job.waiting_reason);
  const readyTranscript =
    transcript.data?.status === "READY" ? transcript.data.transcript : null;
  const conflict =
    saveTranscript.error instanceof ApiError &&
    saveTranscript.error.status === 409;
  const backLinkClass =
    "text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex items-center gap-1.5 rounded-sm transition-colors focus-visible:ring-3";

  async function reloadTranscript() {
    const result = await transcript.refetch();
    if (result.data?.status === "READY" && result.data.transcript) {
      setDraft(result.data.transcript.content);
      setEditBaseVersion(result.data.transcript.source_version);
    }
    saveTranscript.reset();
  }

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
        <Link to="/spaces" className={backLinkClass}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t("record.detail.backToSpaces")}
        </Link>
      )}

      <header className="mt-5 flex min-w-0 items-baseline justify-between gap-4">
        <h1
          className="text-headline font-headline text-ink-strong min-w-0 truncate"
          title={title}
        >
          {title}
        </h1>
        <DeleteRecordDialog
          recordId={detail.id}
          courseId={detail.course_id}
          title={title}
          onDeletingChange={setIsDeleting}
          onDeleted={onDeleted}
        />
      </header>
      <RecordMetadata detail={detail} />

      <Tabs
        value={tab}
        onValueChange={(value) => {
          if (value === "summary" || value === "transcript") onTabChange(value);
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
          {t("record.detail.assetsUnavailable")}
        </p>

        <TabsContent
          value="summary"
          className="border-border mt-6 border-t pt-8"
        >
          <h2 className="text-section font-section text-ink">
            {t(
              detail.status === "FAILED"
                ? "record.detail.failedTitle"
                : "record.detail.summaryEmptyTitle",
            )}
          </h2>
          <p className="max-w-reading text-body text-muted-foreground mt-2">
            {t(
              detail.status === "FAILED"
                ? "record.detail.failedDescription"
                : "record.detail.summaryEmptyDescription",
            )}
          </p>
        </TabsContent>

        <TabsContent
          value="transcript"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
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
                    disabled={detail.status === "SUMMARY_PROCESSING"}
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
              ) : (
                <pre className="text-body text-ink font-body mt-4 min-w-0 font-sans break-words whitespace-pre-wrap">
                  {readyTranscript.content}
                </pre>
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
              {t(`record.detail.jobs.status.${job.status}`)} · {job.attempts}/
              {job.max_attempts}
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
