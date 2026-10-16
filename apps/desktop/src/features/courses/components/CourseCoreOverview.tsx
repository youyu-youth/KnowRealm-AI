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
    <section className="course-overview-heading">
      <div className="min-w-0">
        <h2 className="course-overview-title">
          {t("spaces.courseDetail.coreStats.title")}
        </h2>
        <p className="text-body text-ink-muted mt-2">
          {course.description?.trim() || t("spaces.detail.noDescription")}
        </p>
      </div>
      <div className="course-overview-metrics">
        <StatusTag>{t("spaces.insights.sample")}</StatusTag>
        <dl>
          {metricKeys.map((key) => (
            <div key={key} className="min-w-0">
              <dd className="course-stat">{values[key]}</dd>
              <dt className="text-label text-ink-muted mt-0.5 truncate">
                {t(`spaces.courseDetail.coreStats.${key}`)}
              </dt>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
