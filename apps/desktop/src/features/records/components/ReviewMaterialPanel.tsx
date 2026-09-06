import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "@/components/common/MarkdownContent";
import { ProviderSetupGuide } from "@/components/common/ProviderSetupGuide";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import { settingsApi } from "@/features/settings/api/settings";

type ReviewMaterialPanelProps = {
  recordId: string;
  enabled: boolean;
  onOpenSummary: () => void;
};

type OutlineNode = {
  title: string;
  children: OutlineNode[];
  items: string[];
};

export function ReviewMaterialPanel({
  recordId,
  enabled,
  onOpenSummary,
}: ReviewMaterialPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
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
  if (review.data.active_job_id) {
    return (
      <section className="max-w-reading">
        <Status text={t("record.detail.review.processingTitle")} />
        <p className="text-body text-muted-foreground mt-2">
          {t("record.detail.review.processingDescription")}
        </p>
      </section>
    );
  }
  if (review.data.review_material) {
    const material = review.data.review_material;
    return (
      <div className="max-w-reading min-w-0 space-y-10">
        <section>
          <h2 className="text-section font-section text-ink-strong">
            {t("record.detail.review.quickReviewTitle")}
          </h2>
          <MarkdownContent markdown={material.quick_review} />
        </section>
        <section className="border-border border-t pt-8">
          <h2 className="text-section font-section text-ink-strong">
            {t("record.detail.review.keyListTitle")}
          </h2>
          <ol className="mt-4 space-y-3">
            {material.key_list.map((item, index) => (
              <li
                key={`${index}-${item}`}
                className="text-body text-ink flex gap-3"
              >
                <span className="text-label text-muted-foreground mt-0.5 tabular-nums">
                  {index + 1}.
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="border-border border-t pt-8">
          <h2 className="text-section font-section text-ink-strong">
            {t("record.detail.review.outlineTitle")}
          </h2>
          <OutlineTree markdown={material.mind_map_markdown} />
        </section>
      </div>
    );
  }
  if (review.data.blocked_reason === "SUMMARY_NOT_CONFIRMED") {
    return (
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
  }
  if (review.data.blocked_reason) {
    return (
      <EmptyState
        title={t("record.detail.review.blocked.title")}
        description={t(
          `record.detail.review.blocked.${review.data.blocked_reason}`,
        )}
      />
    );
  }
  if (review.data.action_required === "CONFIGURE_PROVIDER")
    return <ProviderSetupGuide />;
  if (review.data.action_required === "GRANT_CONSENT") {
    return (
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
  }
  const retry = review.data.action_required === "RETRY";
  return (
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

function parseOutline(markdown: string): OutlineNode[] {
  const roots: OutlineNode[] = [];
  const stack: Array<{ level: number; node: OutlineNode }> = [];
  for (const rawLine of markdown.split("\n")) {
    const line = rawLine.trim();
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const node: OutlineNode = { title: heading[2], children: [], items: [] };
      while (stack.length && stack[stack.length - 1].level >= level)
        stack.pop();
      if (stack.length) stack[stack.length - 1].node.children.push(node);
      else roots.push(node);
      stack.push({ level, node });
      continue;
    }
    const item = /^(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line)?.[1];
    if (item && stack.length) stack[stack.length - 1].node.items.push(item);
    else if (item) roots.push({ title: item, children: [], items: [] });
  }
  return roots;
}

function OutlineTree({ markdown }: { markdown: string }) {
  return (
    <div className="mt-4 space-y-2">
      {parseOutline(markdown).map((node) => (
        <OutlineBranch key={node.title} node={node} />
      ))}
    </div>
  );
}

function OutlineBranch({ node }: { node: OutlineNode }) {
  return (
    <details open className="group">
      <summary className="text-body text-ink-strong focus-visible:ring-ring/40 flex cursor-pointer list-none items-center gap-2 rounded-sm py-1 font-medium focus-visible:ring-3">
        <ChevronRight
          className="text-muted-foreground size-4 shrink-0 transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        {node.title}
      </summary>
      <div className="border-border ml-2 border-l pl-5">
        {node.items.length ? (
          <ul className="text-body text-ink list-disc space-y-1 py-2 pl-4">
            {node.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        {node.children.map((child) => (
          <OutlineBranch key={child.title} node={child} />
        ))}
      </div>
    </details>
  );
}
