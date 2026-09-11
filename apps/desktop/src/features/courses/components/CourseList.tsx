import { MoreHorizontal, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Course } from "@/features/courses/api/types";
import {
  CourseAvatar,
  CourseStatusTag,
} from "@/features/courses/components/CourseCard";
import {
  courseTypeLabelKeys,
  learningContextLabelKeys,
} from "@/features/courses/courseOptions";
import { formatCourseMoment } from "@/features/courses/spacesDateFormat";
import { mockCourseStats } from "@/features/courses/spacesInsights";

type CourseListProps = {
  courses: Course[];
  onOpenCourse: (courseId: string) => void;
  onEditCourse: (courseId: string) => void;
  onDeleteCourse: (course: Course) => void;
};

export function CourseList({
  courses,
  onOpenCourse,
  onEditCourse,
  onDeleteCourse,
}: CourseListProps) {
  const { t, i18n } = useTranslation();

  return (
    <ul aria-label={t("spaces.listLabel")} className="grid gap-2">
      {courses.map((course) => {
        const stats = mockCourseStats(course.id);
        const updatedAt = formatCourseMoment(
          course.updated_at,
          t("spaces.time.yesterdayAt"),
          i18n.resolvedLanguage ?? "zh-CN",
        );
        const meta = [
          t(learningContextLabelKeys[course.learning_context]),
          course.course_type
            ? t(courseTypeLabelKeys[course.course_type])
            : null,
          course.description?.trim() || null,
        ]
          .filter((part): part is string => Boolean(part))
          .join(" · ");

        return (
          <li
            key={course.id}
            className="group border-border bg-background hover:border-foreground/20 relative flex min-w-0 items-center rounded-xl border shadow-[0_1px_2px_rgb(15_23_42/0.035)] transition-[border-color,box-shadow] hover:shadow-[0_3px_10px_rgb(15_23_42/0.05)]"
          >
            <button
              type="button"
              onClick={() => onOpenCourse(course.id)}
              aria-label={t("spaces.card.open", { name: course.name })}
              className="focus-visible:ring-ring/40 flex min-w-0 flex-1 items-center gap-3 rounded-xl px-4 py-3 text-left focus-visible:ring-3 focus-visible:outline-hidden"
            >
              <CourseAvatar context={course.learning_context} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className="text-body text-ink-strong truncate font-semibold"
                    title={course.name}
                  >
                    {course.name}
                  </span>
                  <CourseStatusTag course={course} />
                </span>
                <span className="text-label text-ink-faint mt-0.5 block truncate">
                  {meta}
                </span>
              </span>
              <span className="text-label text-ink-muted hidden shrink-0 items-center gap-6 lg:flex">
                <span className="tabular-nums">
                  {t("spaces.card.recordsValue", { count: stats.records })}
                </span>
                <span className="tabular-nums">
                  {t("spaces.card.knowledgePointsValue", {
                    count: stats.knowledgePoints,
                  })}
                </span>
                <time
                  dateTime={course.updated_at}
                  className="w-28 text-right tabular-nums"
                >
                  {updatedAt}
                </time>
              </span>
            </button>
            <div className="bg-background/95 absolute right-3 flex items-center gap-1 rounded-lg pl-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onEditCourse(course.id)}
              >
                {t("spaces.card.editAction")}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      size="icon-sm"
                      variant="outline"
                      aria-label={t("spaces.card.moreActions", {
                        name: course.name,
                      })}
                    />
                  }
                >
                  <MoreHorizontal aria-hidden="true" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-40">
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => onDeleteCourse(course)}
                  >
                    <Trash2 aria-hidden="true" />
                    {t("spaces.delete.action")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
