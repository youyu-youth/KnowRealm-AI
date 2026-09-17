import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { optionLabel } from "@/features/quiz-tests/components/optionLabel";
import {
  TestGradingBlock,
  VerdictTag,
} from "@/features/quiz-tests/components/TestGradingBlock";
import type {
  QuizTestAnswer,
  QuizTestItem,
} from "@/features/quiz-tests/api/types";
import {
  QuizConceptField,
  type QuizConceptChange,
} from "@/features/records/components/QuizConceptField";

type TestQuestionCardProps = {
  item: QuizTestItem;
  /** 记录所属课程：主概念选择器的候选来源 */
  courseId: string | null;
  /** 测试整体不再可作答（已交卷 / 评分中 / 已放弃） */
  locked: boolean;
  /** 本题提交请求在途 */
  pending: boolean;
  /** 终态批改展示（COMPLETED / GRADING_FAILED） */
  reviewing: boolean;
  /** 未提交草稿（由卷面按题持有，切题回看不丢） */
  draft?: QuizTestAnswer;
  onDraftChange: (itemId: string, value: QuizTestAnswer) => void;
  onSubmit: (itemId: string, answer: QuizTestAnswer) => void;
  onConceptUpdated: (quizId: string, concept: QuizConceptChange) => void;
};

export function TestQuestionCard({
  item,
  courseId,
  locked,
  pending,
  reviewing,
  draft,
  onDraftChange,
  onSubmit,
  onConceptUpdated,
}: TestQuestionCardProps) {
  const { t } = useTranslation();
  const answered = item.answered_at !== null;
  const disabled = answered || locked || pending;

  return (
    <article className="border-border border-b py-5 last:border-b-0">
      <div className="flex items-start gap-3">
        <span className="text-body font-section text-ink-strong shrink-0 tabular-nums">
          {item.sequence_no}.
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-label text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-label">
              {t(`record.detail.quiz.type.${item.question_type}`)}
            </span>
            <span>{t(`record.detail.quiz.difficulty.${item.difficulty}`)}</span>
            {item.result ? <VerdictTag result={item.result} /> : null}
          </div>
          <QuizConceptField
            recordId={item.record_id}
            quizId={item.quiz_id}
            courseId={courseId}
            conceptId={item.concept_id}
            conceptName={item.concept_name}
            editable={!disabled}
            onUpdated={(concept) => onConceptUpdated(item.quiz_id, concept)}
          />
          {item.question_type === "FILL_BLANK" ? null : (
            <p className="text-body text-ink mt-2 break-words">{item.stem}</p>
          )}
          {item.question_type === "MULTIPLE_CHOICE" ||
          item.question_type === "TRUE_FALSE" ? (
            <SingleChoiceControl
              item={item}
              disabled={disabled}
              onSelect={(answer) => onSubmit(item.id, answer)}
            />
          ) : item.question_type === "MULTIPLE_SELECT" ? (
            <MultipleSelectControl
              item={item}
              disabled={disabled}
              pending={pending}
              draft={draft}
              onDraftChange={onDraftChange}
              onSubmit={(answer) => onSubmit(item.id, answer)}
            />
          ) : item.question_type === "FILL_BLANK" ? (
            <FillBlankControl
              item={item}
              disabled={disabled}
              pending={pending}
              draft={draft}
              onDraftChange={onDraftChange}
              onSubmit={(answer) => onSubmit(item.id, answer)}
            />
          ) : (
            <ShortAnswerControl
              item={item}
              disabled={disabled}
              pending={pending}
              draft={draft}
              onDraftChange={onDraftChange}
              onSubmit={(answer) => onSubmit(item.id, answer)}
            />
          )}
          {answered && !reviewing ? (
            <p className="text-label text-muted-foreground mt-2">
              {item.result
                ? t("spaces.simulations.paper.submitted")
                : t("spaces.simulations.paper.shortPending")}
            </p>
          ) : null}
          {reviewing && answered ? <TestGradingBlock item={item} /> : null}
          {pending ? (
            <p
              role="status"
              className="text-body text-muted-foreground mt-3 flex items-center gap-2"
            >
              <Spinner aria-hidden="true" />
              {t("spaces.simulations.paper.submitAnswer")}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function SingleChoiceControl({
  item,
  disabled,
  onSelect,
}: {
  item: QuizTestItem;
  disabled: boolean;
  onSelect: (answer: number) => void;
}) {
  const value = typeof item.user_answer === "number" ? item.user_answer : "";
  return (
    <RadioGroup
      className="mt-3 grid gap-2"
      value={value === "" ? "" : String(value)}
      disabled={disabled}
      onValueChange={(next) => onSelect(Number(next))}
    >
      {item.options.map((_option, index) => {
        const id = `test-item-${item.id}-option-${index}`;
        return (
          <Field key={id} orientation="horizontal">
            <RadioGroupItem id={id} value={String(index)} />
            <FieldLabel
              htmlFor={id}
              className="text-body font-body text-ink cursor-pointer"
            >
              {optionLabel(item, index)}
            </FieldLabel>
          </Field>
        );
      })}
    </RadioGroup>
  );
}

function isNumberArray(value: unknown): value is number[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === "number")
  );
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === "string")
  );
}

function SubmitButton({
  pending,
  disabled,
  onClick,
}: {
  pending: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Button
      variant="outline"
      size="sm"
      className="mt-3"
      disabled={disabled}
      onClick={onClick}
    >
      {pending ? <Spinner aria-hidden="true" /> : null}
      {t("spaces.simulations.paper.submitAnswer")}
    </Button>
  );
}

type DraftControlProps = {
  item: QuizTestItem;
  disabled: boolean;
  pending: boolean;
  draft?: QuizTestAnswer;
  onDraftChange: (itemId: string, value: QuizTestAnswer) => void;
};

function MultipleSelectControl({
  item,
  disabled,
  pending,
  draft,
  onDraftChange,
  onSubmit,
}: DraftControlProps & {
  onSubmit: (answer: number[]) => void;
}) {
  const answered = item.answered_at !== null;
  const selected =
    answered && isNumberArray(item.user_answer)
      ? item.user_answer
      : isNumberArray(draft)
        ? draft
        : [];

  const toggle = (index: number, checked: boolean) =>
    onDraftChange(
      item.id,
      checked
        ? [...selected, index].sort((a, b) => a - b)
        : selected.filter((value) => value !== index),
    );

  return (
    <>
      <div className="mt-3 grid gap-2">
        {item.options.map((_option, index) => {
          const id = `test-item-${item.id}-option-${index}`;
          return (
            <Field key={id} orientation="horizontal">
              <Checkbox
                id={id}
                disabled={disabled}
                checked={selected.includes(index)}
                onCheckedChange={(checked) => toggle(index, checked === true)}
              />
              <FieldLabel
                htmlFor={id}
                className="text-body font-body text-ink cursor-pointer"
              >
                {optionLabel(item, index)}
              </FieldLabel>
            </Field>
          );
        })}
      </div>
      {answered ? null : (
        <SubmitButton
          pending={pending}
          disabled={disabled || selected.length === 0}
          onClick={() => onSubmit(selected)}
        />
      )}
    </>
  );
}

function FillBlankControl({
  item,
  disabled,
  pending,
  draft,
  onDraftChange,
  onSubmit,
}: DraftControlProps & {
  onSubmit: (answer: string[]) => void;
}) {
  const { t } = useTranslation();
  const parts = item.stem.split("____");
  const answered = item.answered_at !== null;
  const values =
    answered && isStringArray(item.user_answer)
      ? item.user_answer
      : isStringArray(draft)
        ? draft
        : [];
  const complete =
    values.length === parts.length - 1 &&
    values.every((value) => value.trim() !== "");

  return (
    <>
      <p className="text-body text-ink mt-2 leading-9 break-words">
        {parts.map((part, index) => (
          <span key={`${item.id}-${index}`}>
            {part}
            {index < parts.length - 1 ? (
              <Input
                aria-label={t("record.detail.quiz.fillBlank.blankLabel", {
                  index: index + 1,
                })}
                className="text-body font-body text-ink-strong border-ink/40 mx-2 inline-block h-8 w-28 rounded-none border-0 border-b bg-transparent px-1 py-0.5 text-center shadow-none"
                value={values[index] ?? ""}
                maxLength={100}
                disabled={disabled}
                onChange={(event) =>
                  onDraftChange(
                    item.id,
                    parts
                      .slice(1)
                      .map((_blank, blankIndex) =>
                        blankIndex === index
                          ? event.target.value
                          : (values[blankIndex] ?? ""),
                      ),
                  )
                }
              />
            ) : null}
          </span>
        ))}
      </p>
      {answered ? null : (
        <SubmitButton
          pending={pending}
          disabled={disabled || !complete}
          onClick={() => onSubmit(values)}
        />
      )}
    </>
  );
}

function ShortAnswerControl({
  item,
  disabled,
  pending,
  draft,
  onDraftChange,
  onSubmit,
}: DraftControlProps & {
  onSubmit: (answer: string) => void;
}) {
  const { t } = useTranslation();
  const answered = item.answered_at !== null;
  const draftText = typeof draft === "string" ? draft : "";
  const value =
    answered && typeof item.user_answer === "string"
      ? item.user_answer
      : draftText;

  return (
    <>
      <Textarea
        className="mt-3"
        value={value}
        maxLength={2000}
        rows={4}
        disabled={disabled}
        placeholder={t("spaces.simulations.paper.shortPlaceholder")}
        aria-label={t("spaces.simulations.paper.answerAria", {
          index: item.sequence_no,
        })}
        onChange={(event) => onDraftChange(item.id, event.target.value)}
      />
      {answered ? null : (
        <SubmitButton
          pending={pending}
          disabled={disabled || value.trim().length === 0}
          onClick={() => onSubmit(value)}
        />
      )}
    </>
  );
}
