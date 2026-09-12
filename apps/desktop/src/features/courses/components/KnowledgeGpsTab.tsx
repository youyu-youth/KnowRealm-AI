import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import type { CourseDetail } from "@/features/courses/api/types";
import {
  mockChapterMastery,
  mockCourseCoreStats,
} from "@/features/courses/courseDetailInsights";
import { ChapterMasteryList } from "@/features/courses/components/ChapterMasteryList";

/** 知识GPS 标签页：章级掌握概览 + 明细（示意）。 */
export function KnowledgeGpsTab({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const chapters = mockChapterMastery(course);
  const stats = mockCourseCoreStats(course.id);
  const items = [
    { key: "chapters", value: stats.chapters },
    {
      key: "mastered",
      value: chapters.filter((chapter) => chapter.state === "mastered").length,
    },
    {
      key: "learning",
      value: chapters.filter((chapter) => chapter.state === "learning").length,
    },
    {
      key: "untouched",
      value: chapters.filter((chapter) => chapter.state === "untouched").length,
    },
  ] as const;

  return (
    <SurfaceCard title={t("spaces.courseDetail.gps.tabTitle")} sample>
      <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map((item) => (
          <div
            key={item.key}
            className="border-border-subtle bg-surface-subtle/60 rounded-lg border px-3 py-2.5"
          >
            <dd className="text-stat font-section text-ink-strong tabular-nums">
              {item.value}
            </dd>
            <dt className="text-label text-ink-muted mt-0.5">
              {t(`spaces.courseDetail.gps.summary.${item.key}`)}
            </dt>
          </div>
        ))}
      </dl>
      <div className="mt-5">
        <ChapterMasteryList chapters={chapters} />
      </div>
    </SurfaceCard>
  );
}
