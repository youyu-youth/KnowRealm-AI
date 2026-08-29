import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { ProcessingJobOut, RecordOut } from "@/features/records/api/types";
import { settingsApi } from "@/features/settings/api/settings";
import { ApiError } from "@/services/http/client";

type TranscriptPanelProps = {
  record: RecordOut;
  highlight?: string;
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

  async function reloadTranscript() {
    const result = await transcript.refetch();
    if (result.data?.status === "READY" && result.data.transcript) {
      setDraft(result.data.transcript.content);
      setEditBaseVersion(result.data.transcript.source_version);
    }
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
          ) : (
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
