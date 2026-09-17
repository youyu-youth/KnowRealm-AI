import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockCourseCoreStats } from "@/features/courses/courseDetailInsights";

type MetricKey = "chapters" | "knowledgePoints" | "quizSets";

const metricKeys: MetricKey[] = ["chapters", "knowledgePoints", "quizSets"];

/** 课程核心概览：章节/知识点/习题集（示意）。指标带形态，不做卡片壳。 */
export function CourseCoreOverview({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const stats = mockCourseCoreStats(course.id);
  const values: Record<MetricKey, number> = {
    chapters: stats.chapters,
    knowledgePoints: stats.knowledgePoints,
    quizSets: stats.quizSets,
  };

  return (
    <section className="border-border-subtle min-w-0 border-b pb-5">
      <div className="flex min-w-0 items-center gap-2">
        <h2 className="text-section font-section text-ink-strong">
          {t("spaces.courseDetail.coreStats.title")}
        </h2>
        <StatusTag>{t("spaces.insights.sample")}</StatusTag>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3">
        {metricKeys.map((key) => (
          <div
            key={key}
            className="sm:border-border-subtle min-w-0 sm:border-l sm:pl-4 sm:first:border-l-0 sm:first:pl-0"
          >
            <dd className="text-stat font-section text-ink-strong flex items-baseline gap-1 tabular-nums">
              {values[key]}
              <span className="text-label text-ink-muted">
                {t(`spaces.courseDetail.coreStats.${key}Unit`)}
              </span>
            </dd>
            <dt className="text-label text-ink-muted mt-0.5 truncate">
              {t(`spaces.courseDetail.coreStats.${key}`)}
            </dt>
          </div>
        ))}
      </dl>
    </section>
  );
}
