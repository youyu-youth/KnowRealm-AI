import {
  practiceApi,
  practiceKey,
  type PracticeRound,
} from "@/features/learningPlan/api/practice";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { quizTestKeys } from "@/features/quiz-tests/api/keys";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Button, buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/services/http/client";

/** 本轮计划练习状态卡：作答与评分进度分开，区分可继续/评分中/已结束。 */
export function PracticeRoundCard({
  round,
  courseId,
  itemId,
  editable,
}: {
  round: PracticeRound;
  courseId: string;
  itemId: string;
  editable: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const request = useRef<string | null>(null);
  const retry = useMutation({
    mutationFn: () => {
      request.current ??= crypto.randomUUID();
      return practiceApi.retryGrading(itemId, round.test_id, request.current);
    },
    onSuccess: async () => {
      request.current = null;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: practiceKey(itemId) }),
        queryClient.invalidateQueries({
          queryKey: quizTestKeys.detail(round.test_id),
        }),
      ]);
    },
  });
  const answering = round.status === "IN_PROGRESS";
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
      {round.requirements ? (
        <p className="text-body wrap-anywhere">
          {round.requirements.topic} ·{" "}
          {t("practice.target", { count: round.requirements.question_count })}
        </p>
      ) : null}
      <p className="text-body tabular-nums">
        {round.requirements ? (
          <span className="text-label text-ink-muted block wrap-anywhere">
            {round.requirements.question_types
              .map((type) => t(`practice.type.${type}`))
              .join(" · ")}{" "}
            · {round.sources.map((source) => source.title).join(" · ")}
          </span>
        ) : null}
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
      <Link
        to="/spaces/$courseId/tests/$testId"
        params={{ courseId, testId: round.test_id }}
        search={{ view: "single" }}
        className={buttonVariants({
          variant: "outline",
        })}
      >
        {t(
          answering && editable
            ? "practice.round.continue"
            : "practice.round.result",
        )}
      </Link>
      {round.status === "GRADING" ? (
        <p role="status" className="text-label text-ink-muted">
          {t("practice.round.grading")}
        </p>
      ) : null}
      {round.reused_count ? (
        <p className="text-label text-ink-muted">
          {t("practice.recovery.reused", { count: round.reused_count })}
        </p>
      ) : null}
      {Object.entries(round.grading_errors ?? {}).map(([number, code]) => (
        <p key={number} className="text-label text-danger">
          {t("practice.recovery.itemError", { number })} ·{" "}
          {t(`errors.${code}`, { defaultValue: code })}
        </p>
      ))}
      {round.error_code ? (
        <p role="status" className="text-label text-danger">
          {t(`errors.${round.error_code}`, { defaultValue: round.error_code })}
        </p>
      ) : null}
      {editable && round.retry_available ? (
        <Button
          variant="outline"
          disabled={retry.isPending}
          onClick={() => retry.mutate()}
        >
          {t("practice.recovery.retryGrading")}
        </Button>
      ) : null}
      {retry.isError ? (
        <p role="alert" className="text-body text-danger">
          {retry.error instanceof ApiError
            ? t(`errors.${retry.error.code}`, {
                defaultValue: t("practice.failed"),
              })
            : t("practice.failed")}
        </p>
      ) : null}
    </section>
  );
}
