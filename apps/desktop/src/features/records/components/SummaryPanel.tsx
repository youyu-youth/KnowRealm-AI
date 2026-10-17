import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ProviderSetupGuide } from "@/components/common/ProviderSetupGuide";
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordOut } from "@/features/records/api/types";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { todayKeys } from "@/features/today/api/keys";

type SummaryPanelProps = {
  requestCourseId?: string;
  record: RecordOut;
  onRecordAssetsChanged: () => void | Promise<void>;
};

export function SummaryPanel({
  requestCourseId,
  record,
  onRecordAssetsChanged,
}: SummaryPanelProps) {
  return (
    <>
      <SummaryProviderSettings
        showWhenMissing={record.status === "COMPLETED"}
      />
      <SummaryContent
        requestCourseId={requestCourseId}
        record={record}
        onRecordAssetsChanged={onRecordAssetsChanged}
      />
    </>
  );
}

function SummaryProviderSettings({
  showWhenMissing,
}: {
  showWhenMissing: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const provider = useQuery({
    queryKey: settingsKeys.llmProvider,
    queryFn: settingsApi.getLlmProvider,
  });
  const configured = provider.data?.provider;

  if (!configured?.has_api_key) {
    return showWhenMissing ? <ProviderSetupGuide /> : null;
  }
  return (
    <div className="border-border max-w-reading mb-8 flex flex-wrap items-center justify-between gap-3 border-b pb-5">
      <p className="text-label text-muted-foreground min-w-0 break-all">
        {t("record.detail.summary.configuredProvider", {
          model: configured.model,
          baseUrl: configured.base_url,
        })}
      </p>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void navigate({ to: "/settings" })}
      >
        {t("record.detail.summary.changeProvider")}
      </Button>
    </div>
  );
}

function SummaryContent({
  record,
  onRecordAssetsChanged,
  requestCourseId,
}: SummaryPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const recordId = record.id;
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
      onRecordAssetsChanged(),
      queryClient.invalidateQueries({ queryKey: recordKeys.summary(recordId) }),
      queryClient.invalidateQueries({ queryKey: todayKeys.pendingSummaries }),
    ]);
  const submit = useMutation({
    mutationFn: () => recordApi.submitSummary(recordId, requestCourseId),
    onSuccess: () => void refresh(),
  });
  const upgrade = useMutation({
    mutationFn: () => recordApi.upgrade(recordId, null),
    onSuccess: () => void refresh(),
  });
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
    onSuccess: () => void refresh(),
  });
  useEffect(() => {
    if (!summary.data?.active_job_id && !summary.data?.summary) return;
    void onRecordAssetsChanged();
  }, [
    onRecordAssetsChanged,
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
    if (summary.data.blocked_reason === "COURSE_REQUIRED") {
      return (
        <section className="max-w-reading">
          <h2 className="text-section font-section text-ink">
            {t("record.detail.summary.blockedTitle")}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {t("record.detail.summary.blocked.COURSE_REQUIRED")}
          </p>
          <SummaryCourseUpgradePanel
            record={record}
            onChanged={() => void refresh()}
          />
        </section>
      );
    }
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
    return <ProviderSetupGuide />;
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
      return <ProviderSetupGuide />;
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
    // 已归类 NOTE 只能经升级推进：直接 submit 会因状态不是 SUMMARY_PENDING 被 409 拒绝。
    if (!retry && record.status === "NOTE" && record.course_id) {
      return (
        <SummaryActionState
          title={t("record.detail.summary.emptyTitle")}
          description={t("record.detail.summary.emptyDescription")}
          error={upgrade.error}
          action={t("record.detail.summary.upgrade")}
          pending={upgrade.isPending}
          onAction={() => upgrade.mutate()}
        />
      );
    }
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

function SummaryCourseUpgradePanel({
  record,
  onChanged,
}: {
  record: RecordOut;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [courseId, setCourseId] = useState<string | null>(null);
  const upgrade = useMutation({
    mutationFn: () => recordApi.upgrade(record.id, courseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: recordKeys.inbox() }),
        ...(courseId
          ? [
              queryClient.invalidateQueries({
                queryKey: recordKeys.courseList(courseId),
              }),
            ]
          : []),
      ]);
      onChanged();
    },
  });
  return (
    <div className="mt-5">
      <div className="max-w-reading">
        <ActiveCourseSelect
          id="summary-upgrade-course"
          value={courseId}
          onValueChange={setCourseId}
          disabled={upgrade.isPending}
        />
      </div>
      <Button
        className="mt-5"
        disabled={courseId === null || upgrade.isPending}
        onClick={() => upgrade.mutate()}
      >
        {upgrade.isPending ? (
          <Spinner
            data-icon="inline-start"
            aria-label={t("record.detail.summary.upgrading")}
          />
        ) : null}
        {t("record.detail.summary.classifyAndUpgrade")}
      </Button>
      {upgrade.isError ? (
        <p role="alert" className="text-body text-destructive mt-3">
          {upgrade.error.message}
        </p>
      ) : null}
    </div>
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
