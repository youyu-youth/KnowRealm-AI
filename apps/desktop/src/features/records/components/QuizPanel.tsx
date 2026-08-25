import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { components } from "@knowrealm/api-types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Field,
  FieldLabel,
  FieldSet,
  FieldLegend,
} from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { recordKeys } from "@/features/records/api/keys";
import { recordApi } from "@/features/records/api/records";
import type { QuizOut } from "@/features/records/api/types";
import { settingsApi } from "@/features/settings/api/settings";
import { settingsKeys } from "@/features/settings/api/keys";

const QUIZ_COUNTS = [3, 5, 10] as const;

type QuizCount = (typeof QUIZ_COUNTS)[number];

const ALL_QUESTION_TYPES = [
  "MULTIPLE_CHOICE",
  "TRUE_FALSE",
  "SHORT_ANSWER",
] as const;

type QuizQuestionType = components["schemas"]["QuizQuestionType"];

type QuizPanelProps = {
  recordId: string;
  onOpenSummary: () => void;
};

export function QuizPanel({ recordId, onOpenSummary }: QuizPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const quizzes = useQuery({
    queryKey: recordKeys.quizzes(recordId),
    queryFn: () => recordApi.getQuizzes(recordId),
    refetchInterval: (query) =>
      query.state.data?.active_job_id ? 2_000 : false,
  });
  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: recordKeys.quizzes(recordId),
    });
  const consent = useMutation({
    mutationFn: settingsApi.grantLlmConsent,
    onSuccess: () => void invalidate(),
  });

  if (quizzes.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("record.detail.quiz.loading")}
      </p>
    );
  }
  if (quizzes.isError) {
    return (
      <Empty className="max-w-reading items-start p-0 text-left">
        <EmptyHeader className="items-start text-left">
          <EmptyTitle role="heading" aria-level={2}>
            {t("record.detail.quiz.readErrorTitle")}
          </EmptyTitle>
          <EmptyDescription>{quizzes.error.message}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent className="items-start">
          <Button variant="outline" onClick={() => void quizzes.refetch()}>
            {t("record.detail.retry")}
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  const data = quizzes.data;
  const draftItems = data.items.filter(
    (item) => item.generation_status === "DRAFT",
  );
  const draftBatchId = draftItems[0]?.batch_id ?? null;
  const showSummaryAction =
    data.blocked_reason === "SUMMARY_NOT_CONFIRMED" ||
    data.blocked_reason === "SUMMARY_SUPERSEDED" ||
    data.blocked_reason === "PROVIDER_NOT_CONFIGURED";
  const generateAction =
    !data.active_job_id && !data.blocked_reason && !draftBatchId
      ? data.action_required === "GENERATE" || data.action_required === "RETRY"
        ? data.action_required
        : null
      : null;

  return (
    <div className="max-w-reading min-w-0">
      {draftBatchId ? (
        <QuizCandidateList
          recordId={recordId}
          batchId={draftBatchId}
          items={draftItems}
        />
      ) : null}

      {data.active_job_id ? (
        <section className={draftBatchId ? "mt-8" : undefined}>
          <h2 className="text-section font-section text-ink flex items-center gap-2">
            <Spinner aria-hidden="true" />
            {t("record.detail.quiz.processingTitle")}
          </h2>
          <p role="status" className="text-body text-muted-foreground mt-2">
            {t("record.detail.quiz.processingDescription")}
          </p>
        </section>
      ) : data.blocked_reason ? (
        <Empty className="items-start p-0 text-left">
          <EmptyHeader className="items-start text-left">
            <EmptyTitle role="heading" aria-level={2}>
              {t(`record.detail.quiz.blocked.${data.blocked_reason}.title`)}
            </EmptyTitle>
            <EmptyDescription>
              {t(
                `record.detail.quiz.blocked.${data.blocked_reason}.description`,
              )}
            </EmptyDescription>
          </EmptyHeader>
          {showSummaryAction ? (
            <EmptyContent className="items-start">
              <Button variant="outline" onClick={onOpenSummary}>
                {t("record.detail.quiz.openSummary")}
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
                {t("record.detail.quiz.grantConsent")}
              </Button>
              {consent.isError ? (
                <p role="alert" className="text-body text-destructive">
                  {consent.error.message}
                </p>
              ) : null}
            </EmptyContent>
          ) : null}
        </Empty>
      ) : generateAction === "GENERATE" ? (
        <Empty className="items-start p-0 text-left">
          <EmptyHeader className="items-start text-left">
            <EmptyTitle role="heading" aria-level={2}>
              {t("record.detail.quiz.emptyTitle")}
            </EmptyTitle>
            <EmptyDescription>
              {t("record.detail.quiz.emptyDescription")}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent className="items-start">
            <Button onClick={() => setDialogOpen(true)}>
              {t("record.detail.quiz.generate")}
            </Button>
          </EmptyContent>
        </Empty>
      ) : generateAction === "RETRY" ? (
        <Alert variant="destructive" className="max-w-reading">
          <AlertTitle>{t("record.detail.quiz.failedTitle")}</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <p>{t("record.detail.quiz.failedDescription")}</p>
            <Button variant="outline" onClick={() => setDialogOpen(true)}>
              {t("record.detail.quiz.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <GenerateQuizDialog
        recordId={recordId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}

function QuizCandidateList({
  recordId,
  batchId,
  items,
}: {
  recordId: string;
  batchId: string;
  items: QuizOut[];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: recordKeys.quizzes(recordId),
    });
  const discard = useMutation({
    mutationFn: () => recordApi.discardQuizBatch(recordId, batchId),
    onSuccess: () => void invalidate(),
    onError: () => void invalidate(),
  });

  return (
    <section aria-labelledby="quiz-candidates-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          id="quiz-candidates-title"
          className="text-section font-section text-ink"
        >
          {t("record.detail.quiz.candidatesTitle")}
        </h2>
        <p className="text-label text-muted-foreground">
          {t("record.detail.quiz.candidatesHint", { count: items.length })}
        </p>
      </div>
      <ol className="mt-4">
        {items.map((item, index) => (
          <QuizQuestionCard key={item.id} item={item} index={index} />
        ))}
      </ol>
      <div className="border-border mt-8 flex flex-wrap gap-2 border-t pt-6">
        {confirmingDiscard ? (
          <>
            <Button
              variant="destructive"
              disabled={discard.isPending}
              onClick={() => discard.mutate()}
            >
              {discard.isPending ? <Spinner aria-hidden="true" /> : null}
              {t("record.detail.quiz.discardConfirm")}
            </Button>
            <Button
              variant="outline"
              disabled={discard.isPending}
              onClick={() => setConfirmingDiscard(false)}
            >
              {t("record.detail.quiz.discardCancel")}
            </Button>
          </>
        ) : (
          <Button variant="outline" onClick={() => setConfirmingDiscard(true)}>
            {t("record.detail.quiz.discardBatch")}
          </Button>
        )}
      </div>
      {discard.isError ? (
        <p role="alert" className="text-body text-destructive mt-4">
          {discard.error.message}
        </p>
      ) : null}
    </section>
  );
}

function QuizQuestionCard({ item, index }: { item: QuizOut; index: number }) {
  const { t } = useTranslation();
  const correctIndex =
    typeof item.correct_answer === "number" ? item.correct_answer : null;
  const correctAnswerText =
    correctIndex !== null
      ? `${String.fromCharCode(65 + correctIndex)}. ${item.options[correctIndex]}`
      : item.correct_answer;

  return (
    <li className="border-border border-t py-5 first:border-t-0">
      <article>
        <div className="text-label text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-label">
            {index + 1}. {t(`record.detail.quiz.type.${item.question_type}`)}
          </span>
          <span>{t(`record.detail.quiz.difficulty.${item.difficulty}`)}</span>
        </div>
        <h3 className="text-section font-section text-ink mt-2 break-words">
          {item.stem}
        </h3>
        {item.options.length ? (
          <ul className="text-body text-ink mt-3 list-none space-y-1.5">
            {item.options.map((option, optionIndex) => (
              <li
                key={option}
                className={
                  optionIndex === correctIndex ? "font-medium" : undefined
                }
              >
                {String.fromCharCode(65 + optionIndex)}. {option}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-body text-ink mt-3 whitespace-pre-wrap">
            {t("record.detail.quiz.referenceAnswer", {
              answer: correctAnswerText,
            })}
          </p>
        )}
        {item.options.length ? (
          <p className="text-label text-ink mt-3">
            {t("record.detail.quiz.correctAnswer", {
              answer: correctAnswerText,
            })}
          </p>
        ) : null}
        <p className="text-body text-muted-foreground mt-3 whitespace-pre-wrap">
          {t("record.detail.quiz.explanation", { detail: item.explanation })}
        </p>
      </article>
    </li>
  );
}

function GenerateQuizDialog({
  recordId,
  open,
  onOpenChange,
}: {
  recordId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedTypes, setSelectedTypes] = useState<QuizQuestionType[]>([
    ...ALL_QUESTION_TYPES,
  ]);
  const [totalCount, setTotalCount] = useState<QuizCount>(5);
  const preferences = useQuery({
    queryKey: settingsKeys.preferences,
    queryFn: settingsApi.getPreferences,
  });
  const submit = useMutation({
    mutationFn: (body: components["schemas"]["QuizGenerateRequest"]) =>
      recordApi.submitQuizGeneration(recordId, body),
    onSuccess: async (_data, variables) => {
      onOpenChange(false);
      await Promise.all([
        // 档位记忆是 best-effort：写回失败只影响“记住上次选择”，不干扰生成流程。
        settingsApi
          .updatePreferences({ quiz_last_count: variables.total_count })
          .then(() =>
            queryClient.invalidateQueries({
              queryKey: settingsKeys.preferences,
            }),
          )
          .catch(() => undefined),
        queryClient.invalidateQueries({
          queryKey: recordKeys.quizzes(recordId),
        }),
      ]);
    },
  });
  const preferencesLoaded = open && !preferences.isPending && preferences.data;
  if (preferencesLoaded) {
    const saved = QUIZ_COUNTS.find(
      (count) => count === preferences.data.quiz_last_count,
    );
    if (saved && saved !== totalCount) {
      setTotalCount(saved);
    }
  }

  const toggleType = (type: QuizQuestionType, checked: boolean) => {
    setSelectedTypes((previous) =>
      checked ? [...previous, type] : previous.filter((item) => item !== type),
    );
  };
  const submittable = selectedTypes.length > 0 && !submit.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("record.detail.quiz.dialog.title")}</DialogTitle>
          <DialogDescription>
            {t("record.detail.quiz.dialog.description")}
          </DialogDescription>
        </DialogHeader>
        <FieldSet>
          <FieldLegend variant="label">
            {t("record.detail.quiz.dialog.questionTypes")}
          </FieldLegend>
          <div className="grid gap-2">
            {ALL_QUESTION_TYPES.map((type) => (
              <Field key={type} orientation="horizontal">
                <Checkbox
                  id={`quiz-type-${type}`}
                  checked={selectedTypes.includes(type)}
                  onCheckedChange={(checked) => toggleType(type, checked)}
                />
                <FieldLabel htmlFor={`quiz-type-${type}`}>
                  {t(`record.detail.quiz.type.${type}`)}
                </FieldLabel>
              </Field>
            ))}
          </div>
          {selectedTypes.length === 0 ? (
            <p role="alert" className="text-label text-destructive">
              {t("record.detail.quiz.dialog.typeRequired")}
            </p>
          ) : null}
          <FieldLegend variant="label">
            {t("record.detail.quiz.dialog.totalCount")}
          </FieldLegend>
          <RadioGroup
            value={String(totalCount)}
            onValueChange={(value) => {
              const next = QUIZ_COUNTS.find((count) => String(count) === value);
              if (next) setTotalCount(next);
            }}
            className="grid grid-cols-3 gap-2"
          >
            {QUIZ_COUNTS.map((count) => (
              <Field key={count} orientation="horizontal">
                <RadioGroupItem
                  id={`quiz-count-${count}`}
                  value={String(count)}
                />
                <FieldLabel htmlFor={`quiz-count-${count}`}>{count}</FieldLabel>
              </Field>
            ))}
          </RadioGroup>
        </FieldSet>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={submit.isPending}
            onClick={() => onOpenChange(false)}
          >
            {t("record.detail.quiz.dialog.cancel")}
          </Button>
          <Button
            disabled={!submittable}
            onClick={() =>
              submit.mutate({
                question_types: selectedTypes,
                total_count: totalCount,
              })
            }
          >
            {submit.isPending ? <Spinner aria-hidden="true" /> : null}
            {t("record.detail.quiz.dialog.submit")}
          </Button>
        </DialogFooter>
        {submit.isError ? (
          <p role="alert" className="text-body text-destructive">
            {submit.error.message}
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
