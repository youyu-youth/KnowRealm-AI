import { useTranslation } from "react-i18next";
import type { Course } from "@/features/courses/api/types";

type CourseListProps = {
  courses: Course[];
};

export function CourseList({ courses }: CourseListProps) {
  const { t } = useTranslation();
  const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <ul aria-label={t("spaces.listLabel")} className="mt-8">
      {courses.map((course) => {
        const level = course.education_stage ?? course.depth;
        return (
          <li
            key={course.id}
            className="border-border flex min-h-14 items-center gap-6 border-b py-3 first:border-t"
          >
            <div className="min-w-0 flex-1">
              <p className="text-body text-ink-strong truncate font-semibold">
                {course.name}
              </p>
              <p className="text-label text-muted-foreground mt-1">
                {t(`spaces.learningContext.${course.learning_context}`)}
                {level
                  ? ` · ${t(
                      course.education_stage
                        ? `spaces.educationStage.${course.education_stage}`
                        : `spaces.depth.${course.depth}`,
                    )}`
                  : null}
                {course.course_type
                  ? ` · ${t(`spaces.courseType.${course.course_type}`)}`
                  : null}
              </p>
            </div>
            <time
              dateTime={course.updated_at}
              className="text-label text-muted-foreground shrink-0 tabular-nums"
            >
              {t("spaces.updatedAt", {
                date: dateFormatter.format(new Date(course.updated_at)),
              })}
            </time>
          </li>
        );
      })}
    </ul>
  );
}
