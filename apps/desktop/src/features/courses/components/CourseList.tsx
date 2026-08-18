import { useTranslation } from "react-i18next";
import type { Course } from "@/features/courses/api/types";
import {
  courseDateFormatter,
  courseLevelLabelKey,
  courseTypeLabelKeys,
  learningContextLabelKeys,
} from "@/features/courses/courseOptions";

type CourseListProps = {
  courses: Course[];
  onOpenCourse: (courseId: string) => void;
};

export function CourseList({ courses, onOpenCourse }: CourseListProps) {
  const { t } = useTranslation();

  return (
    <ul aria-label={t("spaces.listLabel")} className="mt-8">
      {courses.map((course) => {
        const levelKey = courseLevelLabelKey(course);
        return (
          <li key={course.id} className="border-border border-b first:border-t">
            <button
              type="button"
              onClick={() => onOpenCourse(course.id)}
              aria-label={course.name}
              className="hover:bg-surface-subtle focus-visible:ring-ring/40 flex min-h-12 w-full cursor-pointer items-center gap-6 rounded-sm px-2 py-1.5 text-left transition-colors focus-visible:ring-3"
            >
              <span className="min-w-0 flex-1">
                <span
                  className="text-body text-ink-strong block truncate font-semibold"
                  title={course.name}
                >
                  {course.name}
                </span>
                <span className="text-label text-muted-foreground mt-1 block">
                  {t(learningContextLabelKeys[course.learning_context])}
                  {levelKey ? ` · ${t(levelKey)}` : null}
                  {course.course_type
                    ? ` · ${t(courseTypeLabelKeys[course.course_type])}`
                    : null}
                </span>
              </span>
              <time
                dateTime={course.updated_at}
                className="text-label text-muted-foreground shrink-0 tabular-nums"
              >
                {t("spaces.updatedAt", {
                  date: courseDateFormatter.format(new Date(course.updated_at)),
                })}
              </time>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
