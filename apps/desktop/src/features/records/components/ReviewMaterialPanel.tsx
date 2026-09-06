import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ProviderSetupGuide } from "@/components/common/ProviderSetupGuide";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import { ReviewMaterialSections } from "@/features/records/components/ReviewMaterialSections";
import { ReviewMaterialWorkbench } from "@/features/records/components/ReviewMaterialWorkbench";
import { settingsApi } from "@/features/settings/api/settings";

type ReviewMaterialPanelProps = {
  recordId: string;
  enabled: boolean;
  onOpenSummary: () => void;
};

export function ReviewMaterialPanel({
  recordId,
  enabled,
  onOpenSummary,
}: ReviewMaterialPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [workbenchOpen, setWorkbenchOpen] = useState(false);
  const sawActiveJobRef = useRef(false);
  const review = useQuery({
    queryKey: recordKeys.reviewMaterial(recordId),
    queryFn: () => recordApi.getReviewMaterial(recordId),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: recordKeys.reviewMaterial(recordId),
    });
  const submit = useMutation({
    mutationFn: () => recordApi.submitReviewMaterial(recordId),
    onSuccess: () => void refresh(),
  });
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
    onSuccess: () => void refresh(),
  });

  // 首次生成完成（active job → v1 落地）自动打开 HITL 工作台；调整完成仅刷新预览
  useEffect(() => {
    if (!enabled || !review.data) return;
    if (review.data.active_job_id) {
      sawActiveJobRef.current = true;
      return;
    }
    const material = review.data.review_material;
    if (sawActiveJobRef.current && material && material.version_no <= 1) {
      setWorkbenchOpen(true);
    }
    sawActiveJobRef.current = false;
  }, [enabled, review.data]);

  if (!enabled) return null;
  if (review.isPending)
    return <Status text={t("record.detail.review.loading")} />;
  if (review.isError) {
    return (
      <section className="max-w-reading">
        <h2 className="text-section font-section text-ink">
          {t("record.detail.review.errorTitle")}
        </h2>
        <p role="alert" className="text-body text-destructive mt-2">
          {review.error.message}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void review.refetch()}
        >
          {t("record.detail.retry")}
        </Button>
      </section>
    );
  }
  let content: ReactNode;
  if (review.data.active_job_id) {
    content = (
      <section className="max-w-reading">
        <Status text={t("record.detail.review.processingTitle")} />
        <p className="text-body text-muted-foreground mt-2">
          {t("record.detail.review.processingDescription")}
        </p>
      </section>
    );
  } else if (review.data.review_material) {
    const material = review.data.review_material;
    const confirmed = material.status === "CONFIRMED";
    content = (
      <>
        <div className="max-w-reading mb-6 flex flex-wrap items-center justify-between gap-3">
          <span
            className={`${
              confirmed
                ? "bg-success/15 text-success"
                : "bg-warning/15 text-warning"
            } text-label font-label rounded-xs px-2 py-1`}
          >
            {t(
              confirmed
                ? "record.detail.review.workbench.versionStatus.CONFIRMED"
                : "record.detail.review.workbench.versionStatus.GENERATED",
            )}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setWorkbenchOpen(true)}
          >
            {t("record.detail.review.workbench.open")}
          </Button>
        </div>
        {review.data.transcript_stale ? (
          <p className="bg-warning/10 text-body text-warning max-w-reading mb-6 rounded-lg px-3 py-2">
            {t("record.detail.review.workbench.staleNotice")}
          </p>
        ) : null}
        <div className="max-w-reading min-w-0">
          <ReviewMaterialSections material={material} />
        </div>
      </>
    );
  } else if (review.data.blocked_reason === "SUMMARY_NOT_CONFIRMED") {
    content = (
      <EmptyState
        title={t("record.detail.review.blocked.summaryTitle")}
        description={t("record.detail.review.blocked.summaryDescription")}
        action={
          <Button onClick={onOpenSummary}>
            {t("record.detail.review.openSummary")}
          </Button>
        }
      />
    );
  } else if (review.data.blocked_reason) {
    content = (
      <EmptyState
        title={t("record.detail.review.blocked.title")}
        description={t(
          `record.detail.review.blocked.${review.data.blocked_reason}`,
        )}
      />
    );
  } else if (review.data.action_required === "CONFIGURE_PROVIDER") {
    content = <ProviderSetupGuide />;
  } else if (review.data.action_required === "GRANT_CONSENT") {
    content = (
      <EmptyState
        title={t("record.detail.review.consentTitle")}
        description={t("record.detail.review.consentDescription")}
        action={
          <Button disabled={consent.isPending} onClick={() => consent.mutate()}>
            {t("record.detail.review.grantConsent")}
          </Button>
        }
        error={consent.error?.message}
      />
    );
  } else {
    const retry = review.data.action_required === "RETRY";
    content = (
      <EmptyState
        title={t(
          retry
            ? "record.detail.review.failedTitle"
            : "record.detail.review.emptyTitle",
        )}
        description={t(
          retry
            ? "record.detail.review.failedDescription"
            : "record.detail.review.emptyDescription",
        )}
        action={
          <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
            {t(
              retry
                ? "record.detail.review.retry"
                : "record.detail.review.generate",
            )}
          </Button>
        }
        error={submit.error?.message}
      />
    );
  }
  return (
    <>
      {content}
      {/* 弹窗挂在稳定位置：生成/调整进行中与阅读态之间切换时不重挂载 */}
      <ReviewMaterialWorkbench
        recordId={recordId}
        open={workbenchOpen}
        onOpenChange={setWorkbenchOpen}
        read={review.data}
      />
    </>
  );
}

function Status({ text }: { text: string }) {
  return (
    <p
      role="status"
      className="text-body text-muted-foreground flex items-center gap-2"
    >
      <Spinner aria-hidden="true" />
      {text}
    </p>
  );
}

function EmptyState({
  title,
  description,
  action,
  error,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  error?: string;
}) {
  return (
    <section className="max-w-reading">
      <h2 className="text-section font-section text-ink">{title}</h2>
      <p className="text-body text-muted-foreground mt-2">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
      {error ? (
        <p role="alert" className="text-body text-destructive mt-3">
          {error}
        </p>
      ) : null}
    </section>
  );
}
