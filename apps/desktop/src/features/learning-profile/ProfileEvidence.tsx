import { Link } from "@tanstack/react-router";
import { Check, FileText, Minus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Ref } from "react";
import type { MasteryEvidenceItem } from "@/features/courses/api/types";
import { cn } from "@/lib/utils";

export function ProfileEvidence({
  courseId,
  evidences,
  example,
  headingRef,
}: {
  courseId: string;
  evidences: MasteryEvidenceItem[];
  example: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const { t, i18n } = useTranslation();
  return (
    <section
      aria-labelledby="profile-evidence-title"
      className="border-border-subtle mt-5 border-t pt-4"
    >
      <h4
        ref={headingRef}
        tabIndex={-1}
        id="profile-evidence-title"
        className="text-body font-section text-ink-strong"
      >
        {t("learningProfile.evidence.title", { count: evidences.length })}
      </h4>
      <p className="text-label text-ink-muted mt-1">
        {t("learningProfile.evidence.scope")}
      </p>
      {evidences.length ? (
        <ol className="mt-3">
          {evidences.map((item) => {
            const source = item.source;
            const Icon =
              item.result === "CORRECT"
                ? Check
                : item.result === "WRONG"
                  ? X
                  : Minus;
            const result =
              item.result === "CORRECT"
                ? "correct"
                : item.result === "WRONG"
                  ? "wrong"
                  : item.result === "PARTIAL"
                    ? "partial"
                    : "scored";
            const sourceLabel = example
              ? t("learningProfile.example.evidence")
              : source?.source_type === "QUIZ"
                ? source.record_title
                : source?.source_type === "QUIZ_TEST"
                  ? t("spaces.courseDetail.gps.detail.sourceTest", {
                      sequence: source.sequence_no ?? "—",
                    })
                  : t("spaces.courseDetail.gps.detail.sourceUnknown");
            return (
              <li
                key={item.evidence_id}
                className="border-border-subtle flex min-w-0 flex-wrap items-start gap-3 border-b py-3 last:border-b-0"
              >
                <span className="bg-surface-subtle flex size-9 shrink-0 items-center justify-center rounded-full">
                  <FileText className="size-5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-body-dense font-label text-ink-strong break-words">
                    {sourceLabel}
                  </p>
                  <p className="text-label text-ink-muted mt-1">
                    {new Date(item.occurred_at).toLocaleDateString(
                      i18n.resolvedLanguage,
                      { year: "numeric", month: "short", day: "numeric" },
                    )}{" "}
                    ·{" "}
                    {t("spaces.courseDetail.gps.percentValue", {
                      percent: Math.round(item.score * 100),
                    })}
                  </p>
                  {example ? (
                    <p className="text-label text-ink-muted mt-2 leading-relaxed">
                      {t("learningProfile.example.answer")}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span
                    className={`text-label ${cn(
                      "inline-flex items-center gap-1 rounded-xs px-2 py-1",
                      result === "correct"
                        ? "bg-success-soft text-success-foreground"
                        : result === "wrong"
                          ? "bg-danger-soft text-destructive"
                          : "bg-surface-subtle text-ink-muted",
                    )}`}
                  >
                    <Icon className="size-3.5" aria-hidden="true" />
                    {t(`learningProfile.evidence.${result}`)}
                  </span>
                  {source ? (
                    source.source_type === "QUIZ" ? (
                      <Link
                        className="text-label text-ink-muted underline underline-offset-4"
                        to="/records/$recordId"
                        params={{ recordId: source.record_id }}
                        search={{ tab: "quiz" }}
                      >
                        {t("learningProfile.evidence.open")}
                      </Link>
                    ) : (
                      <Link
                        className="text-label text-ink-muted underline underline-offset-4"
                        to="/spaces/$courseId/tests/$testId"
                        params={{ courseId, testId: source.test_id }}
                      >
                        {t("learningProfile.evidence.open")}
                      </Link>
                    )
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-body text-ink-muted py-5">
          {t("spaces.courseDetail.gps.detail.evidenceEmpty")}
        </p>
      )}
    </section>
  );
}
