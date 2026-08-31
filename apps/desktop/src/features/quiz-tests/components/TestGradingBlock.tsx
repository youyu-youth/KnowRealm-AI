import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { optionLabel } from "@/features/quiz-tests/components/optionLabel";
import type {
  QuizTestAiGrade,
  QuizTestItem,
  QuizTestItemResult,
} from "@/features/quiz-tests/api/types";

const VERDICT_STYLES: Record<
  QuizTestItemResult | "UNSCORED",
  { tone: string; dot: string }
> = {
  CORRECT: {
    tone: "bg-success-soft text-success-foreground",
    dot: "bg-success-foreground",
  },
  WRONG: { tone: "bg-destructive/10 text-destructive", dot: "bg-destructive" },
  PARTIAL: {
    tone: "bg-warning-soft text-warning-foreground",
    dot: "bg-warning-foreground",
  },
  UNSCORED: {
    tone: "bg-surface-subtle text-muted-foreground",
    dot: "bg-muted-foreground",
  },
};

/** 终态批改标签：答对 / 答错 / 半对 / 未计分（评分失败题） */
export function VerdictTag({ result }: { result: QuizTestItemResult | null }) {
  const { t } = useTranslation();
  const key: QuizTestItemResult | "UNSCORED" = result ?? "UNSCORED";
  const style = VERDICT_STYLES[key];
  return (
    <span
      className={cn(
        "text-label inline-flex items-center gap-1.5 rounded-xs px-1.5 py-0.5",
        style.tone,
      )}
    >
      <span className={cn("size-1.5 rounded-full", style.dot)} />
      {t(`spaces.simulations.paper.verdict.${key}`)}
    </span>
  );
}

function ReviewFlag() {
  const { t } = useTranslation();
  return (
    <span className="text-label bg-warning-soft text-warning-foreground inline-flex items-center gap-1.5 rounded-xs px-1.5 py-0.5">
      <span className="bg-warning-foreground size-1.5 rounded-full" />
      {t("spaces.simulations.paper.review.reviewFlag")}
    </span>
  );
}

function isBlankAccepted(
  item: QuizTestItem,
  index: number,
): { ok: boolean; expected: string } {
  const filled = Array.isArray(item.user_answer)
    ? (item.user_answer[index] ?? "")
    : "";
  const accepted = Array.isArray(item.correct_answer)
    ? item.correct_answer[index]
    : null;
  const expected = Array.isArray(accepted) ? (accepted[0] ?? "") : "";
  const ok =
    Array.isArray(accepted) && accepted.includes(String(filled).trim());
  return { ok, expected };
}

function OptionAnswerLine({ item }: { item: QuizTestItem }) {
  const { t } = useTranslation();
  const label = (index: number) => optionLabel(item, index);
  const yours = Array.isArray(item.user_answer)
    ? item.user_answer.map((index) => label(Number(index))).join("、")
    : item.user_answer != null
      ? label(Number(item.user_answer))
      : "";
  const correct = Array.isArray(item.correct_answer)
    ? item.correct_answer.map((index) => label(Number(index))).join("、")
    : item.correct_answer != null
      ? label(Number(item.correct_answer))
      : "";
  return (
    <>
      <span>
        {t("spaces.simulations.paper.review.yourAnswer", { answer: yours })}
      </span>
      <span>
        {t("spaces.simulations.paper.review.correctAnswer", {
          answer: correct,
        })}
      </span>
    </>
  );
}

function FillBlankLines({ item }: { item: QuizTestItem }) {
  const { t } = useTranslation();
  const blanks = Array.isArray(item.correct_answer)
    ? item.correct_answer.filter((entry) => Array.isArray(entry))
    : [];
  return (
    <div className="space-y-1">
      {blanks.map((_blank, index) => {
        const { ok, expected } = isBlankAccepted(item, index);
        const filled =
          (Array.isArray(item.user_answer)
            ? (item.user_answer[index] ?? "")
            : "") || t("spaces.simulations.paper.review.blankEmpty");
        return (
          <p
            key={index}
            className="text-label text-muted-foreground tabular-nums"
          >
            {t("spaces.simulations.paper.review.blankLine", {
              index: index + 1,
            })}
            <span
              className={ok ? "text-success-foreground" : "text-destructive"}
            >
              {String(filled).trim()}
            </span>
            {ok ? (
              " ✓"
            ) : (
              <span className="text-destructive">
                {" "}
                ✗
                {t("spaces.simulations.paper.review.blankShould", {
                  answer: expected,
                })}
              </span>
            )}
          </p>
        );
      })}
    </div>
  );
}

function ShortAnswerGradeBlock({ aiGrade }: { aiGrade: QuizTestAiGrade }) {
  const { t } = useTranslation();
  if (aiGrade.error_code) {
    return (
      <div className="bg-surface-subtle space-y-1 rounded-xs px-3 py-2.5">
        <p className="text-label text-muted-foreground">
          {t("spaces.simulations.paper.review.gradeFailed", {
            code: aiGrade.error_code,
          })}
        </p>
        <p className="text-label text-muted-foreground">
          {t("spaces.simulations.paper.review.gradeFailedNote")}
        </p>
      </div>
    );
  }
  return (
    <div className="bg-surface-subtle space-y-1.5 rounded-xs px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <VerdictTag result={aiGrade.verdict ?? null} />
        {aiGrade.score != null ? (
          <span className="text-label text-muted-foreground tabular-nums">
            {t("spaces.simulations.paper.review.gradeScore", {
              score: aiGrade.score.toFixed(2),
            })}
          </span>
        ) : null}
        {aiGrade.confidence != null ? (
          <span className="text-label text-muted-foreground tabular-nums">
            {t("spaces.simulations.paper.review.confidence", {
              value: aiGrade.confidence.toFixed(2),
            })}
          </span>
        ) : null}
        {aiGrade.needs_review ? <ReviewFlag /> : null}
      </div>
      {aiGrade.rationale ? (
        <p className="text-body-dense font-body text-ink">
          {t("spaces.simulations.paper.review.rationale", {
            text: aiGrade.rationale,
          })}
        </p>
      ) : null}
    </div>
  );
}

/** 终态批改块：逐题对错、正确答案与解析、简答评分依据与低置信标记 */
export function TestGradingBlock({ item }: { item: QuizTestItem }) {
  const { t } = useTranslation();
  const isShort = item.question_type === "SHORT_ANSWER";
  return (
    <div className="border-border mt-3 space-y-2 border-t pt-3">
      {isShort ? (
        <>
          <p className="text-body-dense font-body text-ink">
            {t("spaces.simulations.paper.review.yourAnswer", {
              answer:
                typeof item.user_answer === "string"
                  ? item.user_answer
                  : t("spaces.simulations.paper.review.blankEmpty"),
            })}
          </p>
          {item.ai_grade ? (
            <ShortAnswerGradeBlock aiGrade={item.ai_grade} />
          ) : null}
          {typeof item.correct_answer === "string" ? (
            <p className="text-label text-muted-foreground">
              {t("spaces.simulations.paper.review.referenceAnswer", {
                answer: item.correct_answer,
              })}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <div className="text-label text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <VerdictTag result={item.result ?? null} />
            {item.question_type === "FILL_BLANK" ? null : (
              <OptionAnswerLine item={item} />
            )}
          </div>
          {item.question_type === "FILL_BLANK" ? (
            <FillBlankLines item={item} />
          ) : null}
        </>
      )}
      {item.explanation ? (
        <p className="text-body-dense font-body text-ink">
          {t("spaces.simulations.paper.review.explanation", {
            text: item.explanation,
          })}
        </p>
      ) : null}
    </div>
  );
}
