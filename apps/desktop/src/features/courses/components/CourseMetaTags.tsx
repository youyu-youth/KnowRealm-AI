import { useTranslation } from "react-i18next";
import type { Course } from "@/features/courses/api/types";
import {
  courseLevelLabelKey,
  courseTypeLabelKeys,
  learningContextLabelKeys,
} from "@/features/courses/courseOptions";

/** 课程场景 / 阶段或深度 / 类型的元信息胶囊组（卡片与详情头共用）。 */
export function CourseMetaTags({
  course,
  className,
}: {
  course: Course;
  className?: string;
}) {
  const { t } = useTranslation();
  const levelKey = courseLevelLabelKey(course);
  return (
    <span
      className={`flex min-w-0 flex-wrap items-center gap-1 ${className ?? ""}`}
    >
      <span className="bg-surface-subtle text-ink-neutral text-label font-label inline-flex h-5 items-center rounded-sm px-1.5 whitespace-nowrap">
        {t(learningContextLabelKeys[course.learning_context])}
      </span>
      {levelKey ? (
        <span className="bg-surface-subtle text-ink-muted text-label font-label inline-flex h-5 items-center rounded-sm px-1.5 whitespace-nowrap">
          {t(levelKey)}
        </span>
      ) : null}
      {course.course_type ? (
        <span className="bg-surface-subtle text-ink-muted text-label font-label inline-flex h-5 items-center rounded-sm px-1.5 whitespace-nowrap">
          {t(courseTypeLabelKeys[course.course_type])}
        </span>
      ) : null}
    </span>
  );
}
