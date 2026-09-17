import { useTranslation } from "react-i18next";
import type { ConceptMastery } from "@/features/courses/api/types";
import { ConceptMasteryBadge } from "@/features/courses/components/ConceptMasteryBadge";
import {
  masteryConfidenceLabelKeys,
  masteryPercentOf,
} from "@/features/courses/masteryStatus";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";
import { cn } from "@/lib/utils";

/** 真实 Concept Mastery 列表：状态、分数、置信度、证据量与最近验证时间；行可打开详情。 */
export function ConceptMasteryList({
  concepts,
  className,
  onSelect,
}: {
  concepts: ConceptMastery[];
  className?: string;
  onSelect?: (concept: ConceptMastery) => void;
}) {
  const { t, i18n } = useTranslation();
  return (
    <ol
      aria-label={t("spaces.courseDetail.gps.conceptListLabel")}
      className={cn("flex flex-col", className)}
    >
      {concepts.map((concept) => {
        const percent = masteryPercentOf(concept.mastery_score);
        const verifiedAt = concept.last_verified_at;
        const practicedAt = concept.last_practiced_at;
        const format = (value: string) =>
          formatCourseMoment(
            value,
            t("spaces.time.yesterdayAt"),
            i18n.resolvedLanguage ?? "zh-CN",
          );
        const meta = verifiedAt
          ? t("spaces.courseDetail.gps.meta", {
              count: concept.evidence_count,
              time: format(verifiedAt),
            })
          : practicedAt
            ? t("spaces.courseDetail.gps.metaPracticed", {
                count: concept.evidence_count,
                time: format(practicedAt),
              })
            : t("spaces.courseDetail.gps.metaNoVerification", {
                count: concept.evidence_count,
              });
        return (
          <li
            key={concept.concept_id}
            className="border-border-subtle border-b last:border-b-0"
          >
            <button
              type="button"
              onClick={() => onSelect?.(concept)}
              className="flex w-full min-w-0 items-center gap-3 py-2.5 text-left"
            >
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="text-body-dense text-ink-strong truncate"
                    title={concept.canonical_name}
                  >
                    {concept.canonical_name}
                  </span>
                  <ConceptMasteryBadge
                    status={concept.status}
                    className="shrink-0"
                  />
                </div>
                <p className="text-label text-ink-muted mt-0.5 truncate">
                  {meta}
                </p>
              </div>
              {percent !== null ? (
                <div className="shrink-0 text-right">
                  <p className="text-section font-section text-ink-strong tabular-nums">
                    {t("spaces.courseDetail.gps.percentValue", { percent })}
                  </p>
                  {concept.confidence ? (
                    <p className="text-label text-ink-muted">
                      {t("spaces.courseDetail.gps.confidence", {
                        level: t(
                          masteryConfidenceLabelKeys[concept.confidence],
                        ),
                      })}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
