import type { PracticeRound } from "@/features/learningPlan/api/practice";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { buttonVariants } from "@/components/ui/button";

/** 本轮计划练习状态卡：作答与评分进度分开，区分可继续/评分中/已结束。 */
export function PracticeRoundCard({
  round,
  courseId,
}: {
  round: PracticeRound;
  courseId: string;
}) {
  const { t } = useTranslation();
  const answering = round.status === "IN_PROGRESS";
  const finished =
    round.status === "COMPLETED" || round.status === "GRADING_FAILED";
  return (
    <section
      aria-label={t("practice.round.cardLabel")}
      className="bg-surface-subtle space-y-3 rounded-lg p-4"
    >
      <h2 className="text-section">
        {t("practice.round.title", { round: round.round_no })} ·{" "}
        {t(`practice.round.status.${round.status}`)}
      </h2>
      <p className="text-label text-ink-muted">
        {t("practice.round.revision", {
          revision: round.requirements_revision,
        })}
      </p>
      <p className="text-body tabular-nums">
        {t("practice.round.progress", {
          answered: round.answered_count,
          graded: round.graded_count,
          total: round.total_count,
        })}
      </p>
      {round.unscored_count > 0 ? (
        <p className="text-label text-ink-muted">
          {t("practice.round.unscored", { count: round.unscored_count })}
        </p>
      ) : null}
      {round.score !== null && round.score_denominator !== null ? (
        <p className="text-body tabular-nums">
          {t("practice.round.score", {
            score: Math.round(round.score * 100),
            denominator: round.score_denominator,
          })}
        </p>
      ) : null}
      {round.sources.some((source) => !source.valid) ? (
        <p role="status" className="text-label text-warning-foreground">
          {t("practice.round.sourceInvalidList", {
            titles: round.sources
              .filter((source) => !source.valid)
              .map((source) => source.title)
              .join("、"),
          })}
        </p>
      ) : null}
      {answering || finished ? (
        <Link
          to="/spaces/$courseId/tests/$testId"
          params={{ courseId, testId: round.test_id }}
          search={{ view: "single" }}
          className={buttonVariants({
            variant: answering ? "default" : "outline",
          })}
        >
          {t(answering ? "practice.round.continue" : "practice.round.result")}
        </Link>
      ) : null}
      {round.status === "GRADING" ? (
        <p role="status" className="text-label text-ink-muted">
          {t("practice.round.grading")}
        </p>
      ) : null}
    </section>
  );
}
