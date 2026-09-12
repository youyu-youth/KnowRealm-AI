import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockChapterMastery } from "@/features/courses/courseDetailInsights";
import { ChapterMasteryList } from "@/features/courses/components/ChapterMasteryList";

/** 知识GPS · 掌握状态：章级掌握列表（示意）。 */
export function CourseMasteryGpsCard({
  course,
  onViewAll,
}: {
  course: CourseDetail;
  onViewAll: () => void;
}) {
  const { t } = useTranslation();
  const chapters = mockChapterMastery(course);

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
      <div className="mt-3">
        <ChapterMasteryList chapters={chapters} />
      </div>
    </SurfaceCard>
  );
}
