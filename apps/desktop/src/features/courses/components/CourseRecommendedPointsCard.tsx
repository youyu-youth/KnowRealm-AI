import { FileText, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { appToast } from "@/components/common/appToastManager";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockRecommendedPoints } from "@/features/courses/courseDetailInsights";

/** 重点知识点推荐：确定性示意数据，「换一批」本地轮转。 */
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
    <SurfaceCard
      title={t("spaces.courseDetail.recommend.title")}
      sample
      action={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setBatch((current) => current + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          {t("spaces.courseDetail.recommend.refresh")}
        </Button>
      }
    >
      <ul key={batch} className="view-switch-enter mt-1 flex flex-col gap-1">
        {points.map((point) => (
          <li
            key={point.id}
            className="hover:bg-surface-subtle -mx-2 flex min-w-0 items-center gap-3 rounded-lg px-2 py-2.5 transition-colors duration-[120ms]"
          >
            <span className="border-border-subtle bg-surface-subtle text-ink-muted flex size-8 shrink-0 items-center justify-center rounded-lg border">
              <FileText className="size-4" aria-hidden="true" />
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
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() =>
                appToast.add({
                  description: t("spaces.courseDetail.recommend.sampleToast"),
                })
              }
            >
              {t("spaces.courseDetail.recommend.go")}
            </Button>
          </li>
        ))}
      </ul>
    </SurfaceCard>
  );
}
