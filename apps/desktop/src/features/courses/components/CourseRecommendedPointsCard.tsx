import { ArrowUpRight, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { appToast } from "@/components/common/appToastManager";
import { StatusTag } from "@/components/common/StatusTag";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockRecommendedPoints } from "@/features/courses/courseDetailInsights";

/** 重点知识点推荐：确定性示意数据，「换一批」本地轮转。列表形态，不做卡片壳。 */
export function CourseRecommendedPointsCard({
  course,
}: {
  course: CourseDetail;
}) {
  const { t } = useTranslation();
  const [batch, setBatch] = useState(0);
  const points = useMemo(
    () => mockRecommendedPoints(course, batch),
    [course, batch],
  );

  return (
    <section className="course-recommendations">
      <header className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-section font-section text-ink-strong min-w-0 truncate">
            {t("spaces.courseDetail.recommend.title")}
          </h2>
          <StatusTag className="shrink-0">
            {t("spaces.insights.sample")}
          </StatusTag>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={() => setBatch((current) => current + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          {t("spaces.courseDetail.recommend.refresh")}
        </Button>
      </header>
      <ul key={batch} className="course-recommendations-list">
        {points.map((point, index) => (
          <li key={point.id} className="course-recommendation">
            <span className="course-recommendation-index" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className="text-body-dense text-ink-strong truncate font-medium"
                title={t(point.titleKey)}
              >
                {t(point.titleKey)}
              </p>
              <p className="text-label text-ink-muted mt-0.5">
                {t("spaces.courseDetail.recommend.meta", {
                  chapter: point.chapter,
                  section: point.section,
                  count: point.learnersK.toFixed(1),
                })}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="course-recommendation-action shrink-0"
              aria-label={`${t("spaces.courseDetail.recommend.go")} ${t(point.titleKey)}`}
              onClick={() =>
                appToast.add({
                  description: t("spaces.courseDetail.recommend.sampleToast"),
                })
              }
            >
              <ArrowUpRight aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
