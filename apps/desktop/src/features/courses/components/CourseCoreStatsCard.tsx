import { BookOpenText, ClipboardList, Layers3, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockCourseCoreStats } from "@/features/courses/courseDetailInsights";

const statItems = [
  {
    key: "chapters",
    icon: BookOpenText,
    iconClass:
      "bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-300",
  },
  {
    key: "knowledgePoints",
    icon: Layers3,
    iconClass:
      "bg-violet-50 text-violet-600 dark:bg-violet-950/50 dark:text-violet-300",
  },
  {
    key: "quizSets",
    icon: ClipboardList,
    iconClass:
      "bg-orange-50 text-orange-600 dark:bg-orange-950/50 dark:text-orange-300",
  },
  {
    key: "mastery",
    icon: TrendingUp,
    iconClass:
      "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
] as const;

/** 课程核心概览：章节/知识点/习题集/掌握度四指标 + 课程寄语（示意）。 */
export function CourseCoreStatsCard({ course }: { course: CourseDetail }) {
  const { t } = useTranslation();
  const stats = mockCourseCoreStats(course.id);
  const values: Record<(typeof statItems)[number]["key"], number> = {
    chapters: stats.chapters,
    knowledgePoints: stats.knowledgePoints,
    quizSets: stats.quizSets,
    mastery: stats.masteryPercent,
  };

  return (
    <SurfaceCard
      title={t("spaces.courseDetail.coreStats.title")}
      sample
      className="@container"
    >
      <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-4 @sm:grid-cols-4">
        {statItems.map(({ key, icon: Icon, iconClass }) => (
          <div key={key} className="flex min-w-0 items-center gap-2.5">
            <span
              className={`${iconClass} flex size-9 shrink-0 items-center justify-center rounded-lg`}
            >
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <dd className="text-section font-section text-ink-strong tabular-nums">
                {t(`spaces.courseDetail.coreStats.${key}Value`, {
                  count: values[key],
                })}
              </dd>
              <dt className="text-label text-ink-muted truncate">
                {t(`spaces.courseDetail.coreStats.${key}`)}
              </dt>
            </div>
          </div>
        ))}
      </dl>
      <blockquote className="border-border-subtle mt-4 border-t pt-3">
        <p className="text-body-dense text-ink-muted leading-relaxed">
          “{t("spaces.courseDetail.coreQuote.text")}”
        </p>
        <footer className="text-label text-ink-faint mt-1.5">
          — KnowRealm
        </footer>
      </blockquote>
    </SurfaceCard>
  );
}
