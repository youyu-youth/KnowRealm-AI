import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  mockChapterMastery,
  mockCurrentProgress,
  mockLearningGoalKey,
} from "@/features/courses/courseDetailInsights";
import { ChapterMasteryList } from "@/features/courses/components/ChapterMasteryList";

/** 概览只展示前几章，完整清单在知识GPS 标签页（分级展示）。 */
const VISIBLE_CHAPTERS = 5;

/** 知识GPS · 掌握状态：进度/目标 + 章级掌握列表（示意）。 */
export function CourseMasteryGpsCard({
  course,
  onViewAll,
}: {
  course: CourseDetail;
  onViewAll: () => void;
}) {
  const { t } = useTranslation();
  const chapters = mockChapterMastery(course);
  const progress = mockCurrentProgress(course);

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.gps.title")}
      sample
      action={
        <Button variant="ghost" size="sm" onClick={onViewAll}>
          {t("spaces.insights.viewAll")}
          <ArrowRight data-icon="inline-end" aria-hidden="true" />
        </Button>
      }
    >
      <dl className="border-border-subtle mt-3 grid grid-cols-2 gap-x-4 border-b pb-3">
        <div className="min-w-0">
          <dt className="text-label text-ink-muted">
            {t("spaces.courseDetail.context.currentProgress")}
          </dt>
          <dd className="text-body-dense text-ink mt-0.5 truncate">
            {t("spaces.courseDetail.context.currentProgressValue", {
              chapter: progress.index,
              name: t(progress.nameKey),
            })}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-label text-ink-muted">
            {t("spaces.courseDetail.context.goal")}
          </dt>
          <dd className="text-body-dense text-ink mt-0.5 truncate">
            {t(mockLearningGoalKey(course))}
          </dd>
        </div>
      </dl>
      <div className="mt-4">
        <ChapterMasteryList chapters={chapters.slice(0, VISIBLE_CHAPTERS)} />
      </div>
    </SurfaceCard>
  );
}
