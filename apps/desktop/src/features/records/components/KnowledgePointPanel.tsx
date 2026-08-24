import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";

type KnowledgePointPanelProps = {
  recordId: string;
  onOpenSummary: () => void;
};

export function KnowledgePointPanel({
  recordId,
  onOpenSummary,
}: KnowledgePointPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const knowledgePoints = useQuery({
    queryKey: recordKeys.knowledgePoints(recordId),
    queryFn: () => recordApi.getKnowledgePoints(recordId),
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const submit = useMutation({
    mutationFn: () => recordApi.submitKnowledgePoints(recordId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: recordKeys.knowledgePoints(recordId),
      }),
  });

  if (knowledgePoints.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("record.detail.knowledgePoints.loading")}
      </p>
    );
  }
  if (knowledgePoints.isError) {
    return (
      <Empty className="max-w-reading items-start p-0 text-left">
        <EmptyHeader className="items-start text-left">
          <EmptyTitle role="heading" aria-level={2}>
            {t("record.detail.knowledgePoints.readErrorTitle")}
          </EmptyTitle>
          <EmptyDescription>{knowledgePoints.error.message}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="items-start">
          <Button
            variant="outline"
            onClick={() => void knowledgePoints.refetch()}
          >
            {t("record.detail.retry")}
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  const data = knowledgePoints.data;
  const summaryOnly = data.input_mode === "SUMMARY_ONLY";
  const showSummaryAction =
    data.blocked_reason === "SUMMARY_NOT_CONFIRMED" ||
    data.blocked_reason === "PROVIDER_NOT_CONFIGURED" ||
    data.blocked_reason === "CONSENT_REQUIRED";

  return (
    <div className="max-w-reading min-w-0">
      {summaryOnly ? (
        <p className="text-label text-warning-foreground bg-warning-soft mb-6 w-fit rounded-sm px-2 py-1">
          {t("record.detail.knowledgePoints.summaryOnly")}
        </p>
      ) : null}

      {data.items.length ? <KnowledgePointList items={data.items} /> : null}

      {data.active_job_id ? (
        <section className={data.items.length ? "mt-8" : undefined}>
          <h2 className="text-section font-section text-ink flex items-center gap-2">
            <Spinner aria-hidden="true" />
            {t("record.detail.knowledgePoints.processingTitle")}
          </h2>
          <p role="status" className="text-body text-muted-foreground mt-2">
            {t("record.detail.knowledgePoints.processingDescription")}
          </p>
        </section>
      ) : data.blocked_reason ? (
        <Empty className="items-start p-0 text-left">
          <EmptyHeader className="items-start text-left">
            <EmptyTitle role="heading" aria-level={2}>
              {t(
                `record.detail.knowledgePoints.blocked.${data.blocked_reason}.title`,
              )}
            </EmptyTitle>
            <EmptyDescription>
              {t(
                `record.detail.knowledgePoints.blocked.${data.blocked_reason}.description`,
              )}
            </EmptyDescription>
          </EmptyHeader>
          {showSummaryAction ? (
            <EmptyContent className="items-start">
              <Button variant="outline" onClick={onOpenSummary}>
                {t("record.detail.knowledgePoints.openSummary")}
              </Button>
            </EmptyContent>
          ) : null}
        </Empty>
      ) : data.action_required === "GENERATE" ? (
        <Empty className="items-start p-0 text-left">
          <EmptyHeader className="items-start text-left">
            <EmptyTitle role="heading" aria-level={2}>
              {t("record.detail.knowledgePoints.emptyTitle")}
            </EmptyTitle>
            <EmptyDescription>
              {t("record.detail.knowledgePoints.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent className="items-start">
            <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
              {submit.isPending ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : null}
              {t("record.detail.knowledgePoints.generate")}
            </Button>
          </EmptyContent>
        </Empty>
      ) : data.action_required === "RETRY" ? (
        <Alert variant="destructive" className="max-w-reading">
          <AlertTitle>
            {t("record.detail.knowledgePoints.failedTitle")}
          </AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <p>{t("record.detail.knowledgePoints.failedDescription")}</p>
            <Button
              variant="outline"
              disabled={submit.isPending}
              onClick={() => submit.mutate()}
            >
              {submit.isPending ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : null}
              {t("record.detail.knowledgePoints.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {submit.isError ? (
        <Alert variant="destructive" className="mt-6">
          <AlertDescription>{submit.error.message}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

type KnowledgePointListProps = {
  items: Awaited<ReturnType<typeof recordApi.getKnowledgePoints>>["items"];
};

function KnowledgePointList({ items }: KnowledgePointListProps) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="knowledge-point-list-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="knowledge-point-list-title"
          className="text-section font-section text-ink"
        >
          {t("record.detail.knowledgePoints.candidatesTitle")}
        </h2>
        <p className="text-label text-muted-foreground">
          {t("record.detail.knowledgePoints.savedLocally")}
        </p>
      </div>
      <ol className="mt-4">
        {items.map((item) => (
          <li
            key={item.id}
            className="border-border border-t py-5 first:border-t-0"
          >
            <article>
              <div className="flex min-w-0 items-baseline justify-between gap-4">
                <h3 className="text-section font-section text-ink min-w-0 break-words">
                  {item.name}
                </h3>
                <span className="text-label text-muted-foreground shrink-0 tabular-nums">
                  {t("record.detail.knowledgePoints.importance", {
                    value: item.importance,
                  })}
                </span>
              </div>
              <p className="text-body text-ink mt-2 whitespace-pre-wrap">
                {item.detail}
              </p>
              {item.tags.length ? (
                <ul
                  aria-label={t("record.detail.knowledgePoints.tagsLabel")}
                  className="text-label text-muted-foreground mt-3 flex flex-wrap gap-x-3 gap-y-1"
                >
                  {item.tags.map((tag) => (
                    <li key={tag}>#{tag}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          </li>
        ))}
      </ol>
    </section>
  );
}
