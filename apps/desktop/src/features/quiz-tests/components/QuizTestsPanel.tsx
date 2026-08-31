import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import {
  Field,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { quizTestKeys } from "@/features/quiz-tests/api/keys";
import { quizTestApi } from "@/features/quiz-tests/api/quizTests";
import {
  QUIZ_QUESTION_TYPES,
  type QuizQuestionType,
  type QuizTestStatus,
} from "@/features/quiz-tests/api/types";

const COUNTS = [5, 10, 20] as const;

const statusClasses: Record<QuizTestStatus, string> = {
  IN_PROGRESS: "bg-learning-soft text-learning-foreground",
  GRADING: "bg-warning-soft text-warning-foreground",
  GRADING_FAILED: "bg-danger/10 text-danger",
  COMPLETED: "bg-success-soft text-success-foreground",
  ABANDONED: "bg-surface-subtle text-neutral-foreground",
};

export function QuizTestsPanel({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const tests = useQuery({
    queryKey: quizTestKeys.list(courseId),
    queryFn: () => quizTestApi.list(courseId),
  });

  if (tests.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2 border-t pt-8"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.simulations.loading")}
      </p>
    );
  }

  if (tests.isError) {
    return (
      <section role="alert" className="border-border border-t pt-8">
        <h2 className="text-section font-section text-ink">
          {t("spaces.simulations.errorTitle")}
        </h2>
        <p className="text-body text-muted-foreground mt-2">
          {t("spaces.simulations.errorDescription")}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void tests.refetch()}
        >
          {t("spaces.simulations.retry")}
        </Button>
      </section>
    );
  }

  if (tests.data.blocked_reason === "COURSE_ARCHIVED") {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground border-t pt-8"
      >
        {t("spaces.simulations.archived")}
      </p>
    );
  }

  return (
    <section className="border-border border-t pt-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-section font-section text-ink">
            {t("spaces.simulations.title")}
          </h2>
          <p className="text-body text-muted-foreground mt-1">
            {t("spaces.simulations.description")}
          </p>
        </div>
        {tests.data.blocked_reason !== "NO_AVAILABLE_QUIZZES" ? (
          <Button onClick={() => setDialogOpen(true)}>
            {t("spaces.simulations.start")}
          </Button>
        ) : null}
      </div>

      {tests.data.items.length === 0 ? (
        <Empty className="items-start rounded-none p-0 pt-8 text-start">
          <EmptyHeader className="items-start text-start">
            <h3 className="text-section font-section text-ink">
              {t(
                tests.data.blocked_reason === "NO_AVAILABLE_QUIZZES"
                  ? "spaces.simulations.noQuestionsTitle"
                  : "spaces.simulations.emptyTitle",
              )}
            </h3>
            <EmptyDescription className="max-w-reading text-body">
              {t(
                tests.data.blocked_reason === "NO_AVAILABLE_QUIZZES"
                  ? "spaces.simulations.noQuestionsDescription"
                  : "spaces.simulations.emptyDescription",
              )}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ul aria-label={t("spaces.simulations.listLabel")} className="mt-5">
          {tests.data.items.map((test) => (
            <li
              key={test.id}
              className="border-border border-b last:border-b-0"
            >
              <Link
                to="/spaces/$courseId/tests/$testId"
                params={{ courseId, testId: test.id }}
                search={{}}
                className="hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-sm px-2 py-4 transition-colors focus-visible:ring-3"
              >
                <div className="min-w-0">
                  <h3 className="text-body font-section text-ink">
                    {t("spaces.simulations.testTitle", {
                      count: test.total_count,
                    })}
                  </h3>
                  <p className="text-label text-muted-foreground mt-1">
                    {t("spaces.simulations.progress", {
                      answered: test.answered_count,
                      total: test.total_count,
                    })}
                  </p>
                </div>
                <span
                  className={`${statusClasses[test.status]} text-label rounded-xs px-2 py-1`}
                >
                  {t(`spaces.simulations.status.${test.status}`)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <CreateQuizTestDialog
        courseId={courseId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onCreated={(testId, selectedCount, shortage) =>
          void navigate({
            to: "/spaces/$courseId/tests/$testId",
            params: { courseId, testId },
            search: shortage ? { shortage: selectedCount } : {},
          })
        }
      />
    </section>
  );
}

function CreateQuizTestDialog({
  courseId,
  open,
  onOpenChange,
  onCreated,
}: {
  courseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (testId: string, selectedCount: number, shortage: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [types, setTypes] = useState<QuizQuestionType[]>([
    ...QUIZ_QUESTION_TYPES,
  ]);
  const [count, setCount] = useState<(typeof COUNTS)[number]>(5);
  const create = useMutation({
    mutationFn: () =>
      quizTestApi.create(courseId, {
        question_types: types,
        total_count: count,
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: quizTestKeys.list(courseId),
      });
      onCreated(result.test.id, result.selected_count, result.shortage);
    },
  });

  const toggleType = (type: QuizQuestionType, checked: boolean) =>
    setTypes((current) =>
      checked ? [...current, type] : current.filter((item) => item !== type),
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("spaces.simulations.dialog.title")}</DialogTitle>
          <DialogDescription>
            {t("spaces.simulations.dialog.description")}
          </DialogDescription>
        </DialogHeader>
        <FieldSet>
          <FieldLegend variant="label">
            {t("spaces.simulations.dialog.types")}
          </FieldLegend>
          <div className="grid gap-2">
            {QUIZ_QUESTION_TYPES.map((type) => (
              <Field key={type} orientation="horizontal">
                <Checkbox
                  id={`test-type-${type}`}
                  checked={types.includes(type)}
                  onCheckedChange={(checked) => toggleType(type, checked)}
                />
                <FieldLabel htmlFor={`test-type-${type}`}>
                  {t(`record.detail.quiz.type.${type}`)}
                </FieldLabel>
              </Field>
            ))}
          </div>
          <FieldLegend variant="label">
            {t("spaces.simulations.dialog.count")}
          </FieldLegend>
          <RadioGroup
            value={String(count)}
            onValueChange={(value) => {
              const next = COUNTS.find((item) => String(item) === value);
              if (next) setCount(next);
            }}
            className="grid grid-cols-3 gap-2"
          >
            {COUNTS.map((item) => (
              <Field key={item} orientation="horizontal">
                <RadioGroupItem
                  id={`test-count-${item}`}
                  value={String(item)}
                />
                <FieldLabel htmlFor={`test-count-${item}`}>
                  {t("spaces.simulations.dialog.countOption", { count: item })}
                </FieldLabel>
              </Field>
            ))}
          </RadioGroup>
        </FieldSet>
        {create.isError ? (
          <p role="alert" className="text-label text-destructive">
            {create.error instanceof Error
              ? create.error.message
              : t("spaces.simulations.dialog.error")}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            onClick={() => create.mutate()}
            disabled={types.length === 0 || create.isPending}
          >
            {create.isPending
              ? t("spaces.simulations.dialog.creating")
              : t("spaces.simulations.dialog.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
