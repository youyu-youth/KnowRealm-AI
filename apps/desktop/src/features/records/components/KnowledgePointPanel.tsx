import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Pencil, Star, Trash2 } from "lucide-react";
import { useId, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { chatApi } from "@/features/chat/api/chatSessions";
import { chatKeys } from "@/features/chat/api/keys";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { KnowledgePointOut } from "@/features/records/api/types";
import { settingsApi } from "@/features/settings/api/settings";
import type { components } from "@knowrealm/api-types";

type KnowledgePointValues = components["schemas"]["KnowledgePointWriteRequest"];

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
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
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
  const summarySuperseded = data.blocked_reason === "SUMMARY_SUPERSEDED";
  const showSummaryAction =
    data.blocked_reason === "SUMMARY_NOT_CONFIRMED" ||
    data.blocked_reason === "PROVIDER_NOT_CONFIGURED" ||
    summarySuperseded;
  const draftBatchId =
    data.items.find((item) => item.generation_status === "DRAFT")?.batch_id ??
    null;
  const canManualAdd = !data.blocked_reason || data.items.length > 0;
  const generateAction =
    !data.active_job_id && !data.blocked_reason
      ? data.action_required === "GENERATE" || data.action_required === "RETRY"
        ? data.action_required
        : null
      : null;
  const generateRetry = generateAction === "RETRY";

  return (
    <div className="max-w-reading min-w-0">
      {summaryOnly ? (
        <p className="text-label text-warning-foreground bg-warning-soft mb-6 w-fit rounded-sm px-2 py-1">
          {t("record.detail.knowledgePoints.summaryOnly")}
        </p>
      ) : null}

      {data.items.length ? (
        <KnowledgePointList
          items={data.items}
          recordId={recordId}
          pendingBatch={draftBatchId !== null}
        />
      ) : null}

      {draftBatchId ? (
        <BatchActions
          recordId={recordId}
          batchId={draftBatchId}
          confirmDisabled={summarySuperseded}
        />
      ) : null}

      {canManualAdd ? <ManualAddSection recordId={recordId} /> : null}

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
          ) : data.blocked_reason === "CONSENT_REQUIRED" ? (
            <EmptyContent className="items-start">
              <Button
                variant="outline"
                disabled={consent.isPending}
                onClick={() => consent.mutate()}
              >
                {consent.isPending ? (
                  <Spinner data-icon="inline-start" aria-hidden="true" />
                ) : null}
                {t("record.detail.knowledgePoints.grantConsent")}
              </Button>
              {consent.isError ? (
                <p role="alert" className="text-body text-destructive">
                  {consent.error.message}
                </p>
              ) : null}
            </EmptyContent>
          ) : null}
        </Empty>
      ) : generateAction && !data.items.length ? (
        generateAction === "GENERATE" ? (
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
              <Button
                disabled={submit.isPending}
                onClick={() => submit.mutate()}
              >
                {submit.isPending ? (
                  <Spinner data-icon="inline-start" aria-hidden="true" />
                ) : null}
                {t("record.detail.knowledgePoints.generate")}
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
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
        )
      ) : generateAction ? (
        <section className="border-border mt-8 border-t pt-6">
          <h2 className="text-section font-section text-ink">
            {t(
              generateRetry
                ? "record.detail.knowledgePoints.failedTitle"
                : "record.detail.knowledgePoints.emptyTitle",
            )}
          </h2>
          <p className="text-body text-muted-foreground mt-2">
            {t(
              generateRetry
                ? "record.detail.knowledgePoints.failedDescription"
                : "record.detail.knowledgePoints.emptyDescription",
            )}
          </p>
          <Button
            className="mt-5"
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
          >
            {submit.isPending ? (
              <Spinner data-icon="inline-start" aria-hidden="true" />
            ) : null}
            {t(
              generateRetry
                ? "record.detail.knowledgePoints.retry"
                : "record.detail.knowledgePoints.generate",
            )}
          </Button>
        </section>
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
  items: KnowledgePointOut[];
  recordId: string;
  pendingBatch: boolean;
};

function KnowledgePointList({
  items,
  recordId,
  pendingBatch,
}: KnowledgePointListProps) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="knowledge-point-list-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="knowledge-point-list-title"
          className="text-section font-section text-ink"
        >
          {t(
            pendingBatch
              ? "record.detail.knowledgePoints.candidatesTitle"
              : "record.detail.knowledgePoints.savedTitle",
          )}
        </h2>
        <p className="text-label text-muted-foreground">
          {t(
            pendingBatch
              ? "record.detail.knowledgePoints.savedLocally"
              : "record.detail.knowledgePoints.savedLocallyActive",
          )}
        </p>
      </div>
      <ol className="mt-4">
        {items.map((item) => (
          <KnowledgePointRow key={item.id} item={item} recordId={recordId} />
        ))}
      </ol>
    </section>
  );
}

function KnowledgePointRow({
  item,
  recordId,
}: {
  item: KnowledgePointOut;
  recordId: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: recordKeys.knowledgePoints(recordId),
    });
  const update = useMutation({
    mutationFn: (values: KnowledgePointValues) =>
      recordApi.updateKnowledgePoint(recordId, item.id, values),
    onSuccess: () => {
      setEditing(false);
      void invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => recordApi.deleteKnowledgePoint(recordId, item.id),
    onSuccess: () => void invalidate(),
  });
  const explain = useMutation({
    mutationFn: () =>
      chatApi.create({
        mode: "ASK",
        record_id: recordId,
        knowledge_point_id: item.id,
      }),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: chatKeys.list() });
      await navigate({
        to: "/chat/$sessionId",
        params: { sessionId: session.id },
        search: {
          prompt: t("record.detail.knowledgePoints.suggestedQuestion", {
            name: item.name,
          }),
        },
      });
    },
  });
  const setImportance = (importance: number) =>
    update.mutate({
      name: item.name,
      detail: item.detail,
      tags: item.tags,
      importance,
    });
  const actionsPending =
    explain.isPending || update.isPending || remove.isPending;
  const mutationError = explain.error ?? update.error ?? remove.error ?? null;

  if (editing) {
    return (
      <li className="border-border border-t py-5 first:border-t-0">
        <KnowledgePointItemForm
          initial={{
            name: item.name,
            detail: item.detail,
            tags: item.tags,
            importance: item.importance,
          }}
          submitLabel={t("record.detail.knowledgePoints.save")}
          pending={update.isPending}
          error={update.error}
          onSubmit={(values) => update.mutate(values)}
          onCancel={() => {
            setEditing(false);
            update.reset();
          }}
        />
      </li>
    );
  }

  return (
    <li className="border-border border-t py-5 first:border-t-0">
      <article>
        <div className="flex min-w-0 items-start justify-between gap-4">
          <h3 className="min-w-0 break-words">
            <Button
              variant="link"
              className="text-section font-section text-ink hover:text-primary h-auto cursor-pointer p-0 text-start whitespace-normal"
              title={t("record.detail.knowledgePoints.explain", {
                name: item.name,
              })}
              disabled={actionsPending}
              onClick={() => explain.mutate()}
            >
              {item.name}
              {explain.isPending ? (
                <Spinner data-icon="inline-end" aria-hidden="true" />
              ) : null}
            </Button>
          </h3>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("record.detail.knowledgePoints.edit", {
                name: item.name,
              })}
              disabled={actionsPending}
              onClick={() => {
                setEditing(true);
                update.reset();
                remove.reset();
              }}
            >
              <Pencil aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("record.detail.knowledgePoints.delete", {
                name: item.name,
              })}
              disabled={actionsPending}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : (
                <Trash2 aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
        <p className="text-body text-ink mt-2 whitespace-pre-wrap">
          {item.detail}
        </p>
        <ImportanceStars
          value={item.importance}
          pending={update.isPending}
          onChange={setImportance}
          itemName={item.name}
        />
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
        {mutationError ? (
          <p role="alert" className="text-body text-destructive mt-3">
            {mutationError.message}
          </p>
        ) : null}
      </article>
    </li>
  );
}

function ImportanceStars({
  value,
  onChange,
  pending = false,
  itemName,
}: {
  value: number;
  onChange?: (value: number) => void;
  pending?: boolean;
  itemName?: string;
}) {
  const { t } = useTranslation();
  const interactive = onChange !== undefined && !pending;
  return (
    <div
      role="group"
      aria-label={t(
        itemName
          ? "record.detail.knowledgePoints.importanceFor"
          : "record.detail.knowledgePoints.importance",
        itemName ? { name: itemName, value } : { value },
      )}
      className="mt-3 flex items-center gap-0.5"
    >
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          aria-label={t(
            itemName
              ? "record.detail.knowledgePoints.setImportanceFor"
              : "record.detail.knowledgePoints.setImportance",
            itemName ? { name: itemName, value: star } : { value: star },
          )}
          aria-pressed={star <= value}
          disabled={!interactive}
          onClick={() => onChange?.(star)}
          className={
            star <= value
              ? "text-ink-strong hover:text-ink cursor-pointer rounded-xs p-0.5 disabled:cursor-default disabled:opacity-100"
              : "text-muted-foreground/50 hover:text-muted-foreground cursor-pointer rounded-xs p-0.5 disabled:cursor-default disabled:opacity-100"
          }
        >
          <Star
            aria-hidden="true"
            className={star <= value ? "size-4 fill-current" : "size-4"}
          />
        </button>
      ))}
      {pending ? <Spinner data-icon="inline-start" aria-hidden="true" /> : null}
    </div>
  );
}

function KnowledgePointItemForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: KnowledgePointValues;
  submitLabel: string;
  pending: boolean;
  error: Error | null;
  onSubmit: (values: KnowledgePointValues) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const formId = useId();
  const [name, setName] = useState(initial.name);
  const [detail, setDetail] = useState(initial.detail);
  const [tags, setTags] = useState(initial.tags.join("，"));
  const [importance, setImportance] = useState(initial.importance);
  const parsedTags = parseTags(tags);
  const submittable =
    name.trim() !== "" &&
    detail.trim() !== "" &&
    parsedTags.length <= 5 &&
    parsedTags.every((tag) => tag.length <= 20) &&
    !pending;

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (submittable) {
          onSubmit({
            name: name.trim(),
            detail: detail.trim(),
            tags: parsedTags,
            importance,
          });
        }
      }}
    >
      <div className="grid gap-2">
        <Label htmlFor={`${formId}-name`}>
          {t("record.detail.knowledgePoints.fieldName")}
        </Label>
        <Input
          id={`${formId}-name`}
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={100}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${formId}-detail`}>
          {t("record.detail.knowledgePoints.fieldDetail")}
        </Label>
        <Textarea
          id={`${formId}-detail`}
          value={detail}
          onChange={(event) => setDetail(event.target.value)}
          rows={4}
          maxLength={2000}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor={`${formId}-tags`}>
          {t("record.detail.knowledgePoints.fieldTags")}
        </Label>
        <Input
          id={`${formId}-tags`}
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder={t("record.detail.knowledgePoints.tagsPlaceholder")}
          aria-describedby={`${formId}-tags-hint`}
        />
        <p
          id={`${formId}-tags-hint`}
          className="text-label text-muted-foreground"
        >
          {t("record.detail.knowledgePoints.tagsHint", {
            current: parsedTags.length,
          })}
        </p>
      </div>
      <div className="grid gap-2">
        <Label>{t("record.detail.knowledgePoints.importanceLabel")}</Label>
        <ImportanceStars value={importance} onChange={setImportance} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!submittable}>
          {pending ? <Spinner aria-hidden="true" /> : null}
          {submitLabel}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending}
          onClick={onCancel}
        >
          {t("record.detail.knowledgePoints.cancel")}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-body text-destructive">
          {error.message}
        </p>
      ) : null}
    </form>
  );
}

function parseTags(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function BatchActions({
  recordId,
  batchId,
  confirmDisabled,
}: {
  recordId: string;
  batchId: string;
  confirmDisabled: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: recordKeys.knowledgePoints(recordId),
    });
  const confirm = useMutation({
    mutationFn: () => recordApi.confirmKnowledgePointBatch(recordId, batchId),
    onSuccess: () => void invalidate(),
    onError: () => void invalidate(),
  });
  const discard = useMutation({
    mutationFn: () => recordApi.discardKnowledgePointBatch(recordId, batchId),
    onSuccess: () => void invalidate(),
    onError: () => void invalidate(),
  });
  const mutationError = confirm.error ?? discard.error ?? null;

  return (
    <section className="border-border max-w-reading mt-8 border-t pt-6">
      <p className="text-body text-muted-foreground">
        {t("record.detail.knowledgePoints.batchActionsHint")}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          disabled={confirmDisabled || confirm.isPending || discard.isPending}
          onClick={() => confirm.mutate()}
        >
          {confirm.isPending ? <Spinner aria-hidden="true" /> : null}
          {t("record.detail.knowledgePoints.confirmBatch")}
        </Button>
        <Button
          variant="destructive"
          disabled={confirm.isPending || discard.isPending}
          onClick={() => discard.mutate()}
        >
          {discard.isPending ? <Spinner aria-hidden="true" /> : null}
          {t("record.detail.knowledgePoints.discardBatch")}
        </Button>
      </div>
      {mutationError ? (
        <p role="alert" className="text-body text-destructive mt-4">
          {mutationError.message}
        </p>
      ) : null}
    </section>
  );
}

function ManualAddSection({ recordId }: { recordId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const create = useMutation({
    mutationFn: (values: KnowledgePointValues) =>
      recordApi.createKnowledgePoint(recordId, values),
    onSuccess: () => {
      setOpen(false);
      create.reset();
      void queryClient.invalidateQueries({
        queryKey: recordKeys.knowledgePoints(recordId),
      });
    },
  });

  return (
    <section className="border-border max-w-reading mt-8 border-t pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-section font-section text-ink">
          {t("record.detail.knowledgePoints.manualAddTitle")}
        </h2>
        {!open ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setOpen(true);
              create.reset();
            }}
          >
            {t("record.detail.knowledgePoints.manualAddToggle")}
          </Button>
        ) : null}
      </div>
      <p className="text-body text-muted-foreground mt-2">
        {t("record.detail.knowledgePoints.manualAddHint")}
      </p>
      {open ? (
        <div className="mt-5">
          <KnowledgePointItemForm
            initial={{ name: "", detail: "", tags: [], importance: 3 }}
            submitLabel={t("record.detail.knowledgePoints.manualAddSubmit")}
            pending={create.isPending}
            error={create.error}
            onSubmit={(values) => create.mutate(values)}
            onCancel={() => {
              setOpen(false);
              create.reset();
            }}
          />
        </div>
      ) : null}
    </section>
  );
}
