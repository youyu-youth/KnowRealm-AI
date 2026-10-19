import { useNavigate, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TodayProgress } from "@/features/today/api/today";

export function TodayPlanFilters({
  courses,
}: {
  courses: TodayProgress["courses"];
}) {
  const { t } = useTranslation();
  const {
    course = "all",
    order = "date",
    action_status: status = "pending",
  } = useSearch({ from: "/" });
  const navigate = useNavigate({ from: "/" });
  const dateSortLabel = t(
    status === "done"
      ? "today.progress.sortCompleted"
      : "today.workspace.sortDate",
  );
  return (
    <div className="today-actions-filters">
      <Select
        value={course}
        onValueChange={(value) =>
          void navigate({
            search: (previous) => ({
              ...previous,
              course: value ?? "all",
              completed_page: 1,
            }),
            replace: true,
          })
        }
      >
        <SelectTrigger
          size="sm"
          aria-label={t("today.workspace.courseFilter")}
          className="text-label max-w-40"
        >
          <SelectValue>
            {course === "all"
              ? t("today.workspace.allCourses")
              : (courses.find((item) => item.course_id === course)
                  ?.course_name ?? t("today.progress.selectedCourse"))}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("today.workspace.allCourses")}</SelectItem>
          {courses.map((item) => (
            <SelectItem key={item.course_id} value={item.course_id}>
              {item.course_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={order}
        onValueChange={(value) =>
          void navigate({
            search: (previous) => ({
              ...previous,
              order: value === "duration" ? "duration" : "date",
              completed_page: 1,
            }),
            replace: true,
          })
        }
      >
        <SelectTrigger
          size="sm"
          aria-label={t("today.workspace.sort")}
          title={
            order === "duration"
              ? t("today.workspace.sortDuration")
              : dateSortLabel
          }
          className="text-label"
        >
          <SelectValue>
            {order === "duration"
              ? t("today.workspace.sortDurationShort")
              : t(
                  status === "done"
                    ? "today.progress.sortCompletedShort"
                    : "today.workspace.sortDateShort",
                )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="date">{dateSortLabel}</SelectItem>
          <SelectItem value="duration">
            {t("today.workspace.sortDuration")}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
