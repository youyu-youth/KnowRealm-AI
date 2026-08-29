import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ActiveCourseSelect } from "@/features/courses/components/ActiveCourseSelect";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { RecordOut } from "@/features/records/api/types";
import { settingsKeys } from "@/features/settings/api/keys";
import { settingsApi } from "@/features/settings/api/settings";
import { todayKeys } from "@/features/today/api/keys";

type SummaryPanelProps = {
  record: RecordOut;
  onRecordAssetsChanged: () => void | Promise<void>;
};

export function SummaryPanel({
  record,
  onRecordAssetsChanged,
}: SummaryPanelProps) {
  return (
    <>
      <SummaryProviderSettings
        showWhenMissing={record.status === "COMPLETED"}
        onChanged={onRecordAssetsChanged}
      />
      <SummaryContent
        record={record}
        onRecordAssetsChanged={onRecordAssetsChanged}
      />
    </>
  );
}

function SummaryProviderSettings({
  showWhenMissing,
  onChanged,
}: {
  showWhenMissing: boolean;
  onChanged: () => void | Promise<void>;
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
            void onChanged();
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

function SummaryContent({ record, onRecordAssetsChanged }: SummaryPanelProps) {
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
    mutationFn: () => recordApi.submitSummary(recordId),
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

function ProviderConfiguration({
  onSaved,
  onCancel,
}: {
  onSaved: () => void | Promise<void>;
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
          <Button type="button" variant="ghost" onClick={() => void onSaved()}>
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
