import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, Pencil } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { ProcessingJobOut, RecordOut } from "@/features/records/api/types";
import { DeleteRecordDialog } from "@/features/records/components/DeleteRecordDialog";
import { KnowledgePointPanel } from "@/features/records/components/KnowledgePointPanel";
import {
  captureTypeLabelKeys,
  formatRecordDuration,
  recordDateFormatter,
  statusClassNames,
  statusLabelKeys,
} from "@/features/records/recordPresentation";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";
import { todayKeys } from "@/features/today/api/keys";
import { ApiError } from "@/services/http/client";

type RecordDetailPageProps = {
  recordId: string;
  tab: "summary" | "transcript" | "knowledge-points";
  onTabChange: (tab: "summary" | "transcript" | "knowledge-points") => void;
  onDeleted: (courseId: string | null) => void | Promise<void>;
};

const unavailableTabs = [
  { value: "quiz", labelKey: "record.detail.tabs.quiz" },
  { value: "review", labelKey: "record.detail.tabs.review" },
  { value: "todo", labelKey: "record.detail.tabs.todo" },
  { value: "ask-ai", labelKey: "record.detail.tabs.askAi" },
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
      queryClient.invalidateQueries({ queryKey: recordKeys.summary(recordId) }),
      queryClient.invalidateQueries({
        queryKey: recordKeys.knowledgePoints(recordId),
      }),
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
          if (
            value === "summary" ||
            value === "transcript" ||
            value === "knowledge-points"
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
          <SummaryProviderSettings
            showWhenMissing={detail.status === "COMPLETED"}
            onChanged={() => void invalidateRecord()}
          />
          <SummaryPanel recordId={recordId} />
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

        <TabsContent
          value="knowledge-points"
          className="border-border mt-6 min-w-0 border-t pt-8"
        >
          <KnowledgePointPanel
            recordId={recordId}
            onOpenSummary={() => onTabChange("summary")}
          />
        </TabsContent>
      </Tabs>
    </section>
  );
}

function SummaryProviderSettings({
  showWhenMissing,
  onChanged,
}: {
  showWhenMissing: boolean;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: settingsApi.getLlmProvider,
  });
  const configured = provider.data?.provider;

  if (!configured?.has_api_key) {
    return showWhenMissing ? (
      <ProviderConfiguration onSaved={onChanged} />
    ) : null;
  }
  if (editing) {
    return (
      <div className="border-border mb-8 border-b pb-8">
        <ProviderConfiguration
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </div>
    );
  }
  return (
    <div className="border-border max-w-reading mb-8 flex flex-wrap items-center justify-between gap-3 border-b pb-5">
      <p className="text-label text-muted-foreground min-w-0 break-all">
        {t("record.detail.summary.configuredProvider", {
          model: configured.model,
          baseUrl: configured.base_url,
        })}
      </p>
      <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
        {t("record.detail.summary.changeProvider")}
      </Button>
    </div>
  );
}

function SummaryPanel({ recordId }: { recordId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: settingsApi.getLlmProvider,
  });
  const summary = useQuery({
    queryKey: recordKeys.summary(recordId),
    queryFn: () => recordApi.getSummary(recordId),
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: recordKeys.detail(recordId) }),
      queryClient.invalidateQueries({ queryKey: recordKeys.summary(recordId) }),
      // 总结确认可能解除知识点重新生成锁定，需一并失效
      queryClient.invalidateQueries({
        queryKey: recordKeys.knowledgePoints(recordId),
      }),
      queryClient.invalidateQueries({ queryKey: todayKeys.pendingSummaries }),
    ]);
  const submit = useMutation({
    mutationFn: () => recordApi.submitSummary(recordId),
    onSuccess: () => void refresh(),
  });
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
    onSuccess: () => void refresh(),
  });
  useEffect(() => {
    if (!summary.data?.active_job_id && !summary.data?.summary) return;
    void queryClient.invalidateQueries({
      queryKey: recordKeys.detail(recordId),
    });
  }, [
    queryClient,
    recordId,
    summary.data?.active_job_id,
    summary.data?.summary,
  ]);

  if (summary.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("record.detail.summary.loading")}
      </p>
    );
  }
  if (summary.isError) {
    return (
      <section className="max-w-reading">
        <h2 className="text-section font-section text-ink">
          {t("record.detail.summary.errorTitle")}
        </h2>
        <p role="alert" className="text-body text-destructive mt-2">
          {summary.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void summary.refetch()}
        >
          {t("record.detail.retry")}
        </Button>
      </section>
    );
  }

  if (summary.data.summary) {
    const content = summary.data.summary;
    const confirmed = content.status === "CONFIRMED";
    return (
      <>
        <article className="max-w-reading min-w-0">
          <p className="text-label text-muted-foreground">
            {t(
              confirmed
                ? "record.detail.summary.confirmedLabel"
                : "record.detail.summary.pendingConfirmation",
            )}
          </p>
          <h2 className="text-headline font-headline text-ink-strong mt-2">
            {content.topic}
          </h2>
          <p className="text-body text-ink mt-5 whitespace-pre-wrap">
            {content.abstract}
          </p>
          {content.sections.map((section) => (
            <section
              key={section.heading}
              className="border-border mt-8 border-t pt-6"
            >
              <h3 className="text-section font-section text-ink">
                {section.heading}
              </h3>
              <ul className="text-body text-ink mt-3 list-disc space-y-2 pl-5">
                {section.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </section>
          ))}
        </article>
        {!confirmed ? (
          <SummaryReviewActions
            recordId={recordId}
            summaryId={content.id}
            onChanged={() => void refresh()}
          />
        ) : null}
      </>
    );
  }

  if (summary.data.blocked_reason) {
    return (
      <SummaryActionState
        title={t("record.detail.summary.blockedTitle")}
        description={t(
          `record.detail.summary.blocked.${summary.data.blocked_reason}`,
        )}
      />
    );
  }
  if (summary.data.action_required === "CONFIGURE_PROVIDER") {
    return <ProviderConfiguration onSaved={() => void refresh()} />;
  }
  if (summary.data.action_required === "GRANT_CONSENT") {
    if (provider.isPending) {
      return (
        <SummaryActionState
          title={t("record.detail.summary.providerTitle")}
          description={t("record.detail.summary.loading")}
          pending
        />
      );
    }
    if (provider.isError) {
      return (
        <SummaryActionState
          title={t("record.detail.summary.providerTitle")}
          description={provider.error.message}
          action={t("record.detail.retry")}
          onAction={() => void provider.refetch()}
        />
      );
    }
    if (!provider.data.provider?.has_api_key) {
      return <ProviderConfiguration onSaved={() => void refresh()} />;
    }
    return (
      <SummaryActionState
        title={t("record.detail.summary.consentTitle")}
        description={t("record.detail.summary.consentDisclosure")}
        error={consent.error}
        action={t("record.detail.summary.grantConsent")}
        pending={consent.isPending}
        onAction={() => consent.mutate()}
      />
    );
  }
  if (["GENERATE", "RETRY"].includes(summary.data.action_required)) {
    const retry = summary.data.action_required === "RETRY";
    return (
      <SummaryActionState
        title={t(
          retry
            ? "record.detail.summary.failedTitle"
            : "record.detail.summary.emptyTitle",
        )}
        description={t(
          retry
            ? "record.detail.summary.failedDescription"
            : "record.detail.summary.emptyDescription",
        )}
        error={submit.error}
        action={t(
          retry
            ? "record.detail.summary.retry"
            : "record.detail.summary.generate",
        )}
        pending={submit.isPending}
        onAction={() => submit.mutate()}
      />
    );
  }
  return (
    <SummaryActionState
      title={t("record.detail.summary.processingTitle")}
      description={t("record.detail.summary.processingDescription")}
      pending
    />
  );
}

function SummaryReviewActions({
  recordId,
  summaryId,
  onChanged,
}: {
  recordId: string;
  summaryId: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [adjusting, setAdjusting] = useState(false);
  const [feedback, setFeedback] = useState("");
  const confirm = useMutation({
    mutationFn: () => recordApi.confirmSummary(recordId, summaryId),
    onSuccess: onChanged,
    onError: onChanged,
  });
  const adjust = useMutation({
    mutationFn: (text: string) =>
      recordApi.adjustSummary(recordId, {
        summary_id: summaryId,
        feedback: text,
      }),
    onSuccess: () => {
      setAdjusting(false);
      setFeedback("");
      onChanged();
    },
    onError: onChanged,
  });
  const mutationError = confirm.error ?? adjust.error ?? null;

  return (
    <section className="border-border max-w-reading mt-8 border-t pt-6">
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={confirm.isPending || adjust.isPending}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending ? <Spinner aria-hidden="true" /> : null}
          {t("record.detail.summary.confirm")}
        </Button>
        {!adjusting ? (
          <Button
            variant="outline"
            disabled={confirm.isPending || adjust.isPending}
            onClick={() => {
              setAdjusting(true);
              adjust.reset();
            }}
          >
            {t("record.detail.summary.adjust")}
          </Button>
        ) : null}
      </div>
      {adjusting ? (
        <form
          className="mt-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (feedback.trim()) adjust.mutate(feedback.trim());
          }}
        >
          <Label htmlFor="summary-adjust-feedback">
            {t("record.detail.summary.adjustFeedbackLabel")}
          </Label>
          <Textarea
            id="summary-adjust-feedback"
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            rows={4}
            maxLength={1000}
            className="mt-2"
            placeholder={t("record.detail.summary.adjustFeedbackPlaceholder")}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="submit"
              disabled={!feedback.trim() || adjust.isPending}
            >
              {adjust.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("record.detail.summary.submitAdjustment")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={adjust.isPending}
              onClick={() => {
                setAdjusting(false);
                setFeedback("");
                adjust.reset();
              }}
            >
              {t("record.detail.summary.cancelAdjustment")}
            </Button>
          </div>
        </form>
      ) : null}
      {mutationError ? (
        <p role="alert" className="text-body text-destructive mt-4">
          {mutationError.message}
        </p>
      ) : null}
    </section>
  );
}

function SummaryActionState({
  title,
  description,
  action,
  pending = false,
  error,
  onAction,
}: {
  title: string;
  description: string;
  action?: string;
  pending?: boolean;
  error?: Error | null;
  onAction?: () => void;
}) {
  return (
    <section className="max-w-reading">
      <h2 className="text-section font-section text-ink flex items-center gap-2">
        {pending && !action ? <Spinner aria-hidden="true" /> : null}
        {title}
      </h2>
      <p className="text-body text-muted-foreground mt-2">{description}</p>
      {action && onAction ? (
        <Button className="mt-5" disabled={pending} onClick={onAction}>
          {pending ? <Spinner aria-hidden="true" /> : null}
          {action}
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

function ProviderConfiguration({
  onSaved,
  onCancel,
}: {
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: settingsApi.getLlmProvider,
  });
  const save = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      return settingsApi.updateLlmProvider({
        base_url: String(data.get("base_url") ?? ""),
        model: String(data.get("model") ?? ""),
        api_key: String(data.get("api_key") ?? ""),
        clear_api_key: data.get("clear_api_key") === "on",
      });
    },
    onSuccess: (updated, form) => {
      const apiKey = form.elements.namedItem("api_key");
      const clearApiKey = form.elements.namedItem("clear_api_key");
      if (apiKey instanceof HTMLInputElement) apiKey.value = "";
      if (clearApiKey instanceof HTMLInputElement) clearApiKey.checked = false;
      queryClient.setQueryData(settingsKeys.llmProvider, updated);
    },
  });
  const test = useMutation({ mutationFn: settingsApi.testLlmProvider });

  if (provider.isPending) {
    return (
      <SummaryActionState
        title={t("record.detail.summary.providerTitle")}
        description={t("record.detail.summary.loading")}
        pending
      />
    );
  }

  return (
    <form
      className="max-w-reading"
      onChange={() => {
        save.reset();
        test.reset();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(event.currentTarget);
      }}
    >
      <h2 className="text-section font-section text-ink">
        {t("record.detail.summary.providerTitle")}
      </h2>
      <p className="text-body text-muted-foreground mt-2">
        {t("record.detail.summary.providerDescription")}
      </p>
      <div className="mt-6 grid gap-5">
        <div className="grid gap-2">
          <Label htmlFor="llm-base-url">
            {t("record.detail.summary.baseUrl")}
          </Label>
          <Input
            id="llm-base-url"
            name="base_url"
            type="url"
            required
            defaultValue={
              provider.data?.provider?.base_url ??
              "https://dashscope.aliyuncs.com/compatible-mode/v1"
            }
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="llm-model">{t("record.detail.summary.model")}</Label>
          <Input
            id="llm-model"
            name="model"
            required
            defaultValue={provider.data?.provider?.model ?? "qwen-plus"}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="llm-api-key">
            {t("record.detail.summary.apiKey")}
          </Label>
          <Input
            id="llm-api-key"
            name="api_key"
            type="password"
            placeholder={
              provider.data?.provider?.api_key_hint ??
              t("record.detail.summary.apiKeyPlaceholder")
            }
          />
        </div>
        {provider.data?.provider?.has_api_key ? (
          <Label>
            <input type="checkbox" name="clear_api_key" />
            {t("record.detail.summary.clearApiKey")}
          </Label>
        ) : null}
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? <Spinner aria-hidden="true" /> : null}
          {t("record.detail.summary.saveProvider")}
        </Button>
        {save.data?.provider?.has_api_key ||
        provider.data?.provider?.has_api_key ? (
          <Button
            variant="outline"
            type="button"
            disabled={test.isPending}
            onClick={() => test.mutate()}
          >
            {test.isPending ? <Spinner aria-hidden="true" /> : null}
            {t("record.detail.summary.testProvider")}
          </Button>
        ) : null}
        {save.isSuccess ? (
          <Button type="button" variant="ghost" onClick={onSaved}>
            {t("record.detail.summary.continue")}
          </Button>
        ) : null}
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel}>
            {t("record.detail.summary.cancelProviderEdit")}
          </Button>
        ) : null}
      </div>
      {test.isSuccess ? (
        <p role="status" className="text-body text-muted-foreground mt-3">
          {t("record.detail.summary.testSucceeded", { model: test.data.model })}
        </p>
      ) : null}
      {provider.isError || save.isError || test.isError ? (
        <p role="alert" className="text-body text-destructive mt-3">
          {(provider.error ?? save.error ?? test.error)?.message}
        </p>
      ) : null}
    </form>
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
