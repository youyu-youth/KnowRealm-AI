import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { CourseDetail } from "@/features/courses/api/types";
import { useCourseMastery } from "@/features/courses/api/queries";
import { MasteryStatusCounts } from "@/features/courses/components/MasteryStatusCounts";

/** 概览 · 知识GPS：已确认概念数、证据覆盖率与四类状态分布（真实数据）。 */
export function CourseMasteryGpsCard({
  course,
  onViewAll,
  onOpenBrain,
}: {
  course: CourseDetail;
  onViewAll: () => void;
  onOpenBrain: () => void;
}) {
  const { t } = useTranslation();
  const mastery = useCourseMastery(course.id);

  return (
    <SurfaceCard
      className="course-overview-section course-mastery"
      title={t("spaces.courseDetail.gps.title")}
      action={
        <Button variant="ghost" size="sm" onClick={onViewAll}>
          {t("spaces.insights.viewAll")}
          <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </Button>
      }
    >
      {mastery.isPending ? (
        <p
          role="status"
          className="text-body text-ink-muted mt-3 flex items-center gap-2"
        >
          <Spinner aria-hidden="true" />
          {t("spaces.courseDetail.gps.loading")}
        </p>
      ) : null}

      {mastery.isError ? (
        <div className="mt-3 flex flex-col items-start gap-2">
          <p className="text-body-dense text-ink-strong">
            {t("spaces.courseDetail.gps.errorTitle")}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void mastery.refetch()}
          >
            {t("spaces.courseDetail.gps.retry")}
          </Button>
        </div>
      ) : null}

      {mastery.data ? (
        mastery.data.confirmed_concept_count === 0 ? (
          <div className="mt-3 flex flex-col items-start gap-2">
            <p className="text-body-dense text-ink-strong">
              {t("spaces.courseDetail.gps.emptyTitle")}
            </p>
            <p className="text-label text-ink-muted">
              {t("spaces.courseDetail.gps.emptyDescription")}
            </p>
            <Button variant="outline" size="sm" onClick={onOpenBrain}>
              {t("spaces.courseDetail.gps.emptyAction")}
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex min-w-0 flex-col gap-4">
            <div className="course-mastery-summary">
              <dl className="grid grid-cols-2 gap-x-4">
                <div className="min-w-0">
                  <dd className="course-stat">
                    {mastery.data.confirmed_concept_count}
                  </dd>
                  <dt className="text-label text-ink-muted mt-0.5">
                    {t("spaces.courseDetail.gps.confirmedConcepts")}
                  </dt>
                </div>
                <div className="min-w-0">
                  <dd className="course-stat">
                    {t("spaces.courseDetail.gps.percentValue", {
                      percent: Math.round(mastery.data.coverage * 100),
                    })}
                  </dd>
                  <dt className="text-label text-ink-muted mt-0.5">
                    {t("spaces.courseDetail.gps.coverage")}
                  </dt>
                </div>
              </dl>
              <div className="course-mastery-description">
                <p className="text-body-dense font-medium">
                  {t(
                    mastery.data.verified_concept_count === 0
                      ? "spaces.courseDetail.gps.evidenceEmptyTitle"
                      : "spaces.courseDetail.gps.evidenceTitle",
                  )}
                </p>
                <p className="text-label text-ink-muted mt-1">
                  {t("spaces.courseDetail.gps.evidenceDescription", {
                    total: mastery.data.confirmed_concept_count,
                    verified: mastery.data.verified_concept_count,
                  })}
                </p>
              </div>
            </div>
            <MasteryStatusCounts
              counts={mastery.data.status_counts}
              className="course-mastery-counts"
              itemClassName="gap-2"
              valueClassName="w-6 shrink-0"
            />
          </div>
        )
      ) : null}
    </SurfaceCard>
  );
}
