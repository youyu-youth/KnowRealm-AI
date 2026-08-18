import { createFileRoute } from "@tanstack/react-router";
import type { CourseListQuery } from "@/features/courses/api/types";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
import {
  isCourseType,
  isEducationStage,
} from "@/features/courses/courseOptions";

export const Route = createFileRoute("/spaces/")({
  validateSearch: (search): CourseListQuery => {
    const q = typeof search.q === "string" ? search.q.trim() : "";
    return {
      q: q.length > 0 && q.length <= 100 ? q : undefined,
      education_stage: isEducationStage(search.education_stage)
        ? search.education_stage
        : undefined,
      course_type: isCourseType(search.course_type)
        ? search.course_type
        : undefined,
    };
  },
  component: SpacesPage,
});

export function SpacesPage() {
  const filters = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CoursesPage
      filters={filters}
      onFiltersChange={(search) => void navigate({ search, replace: true })}
      onOpenCourse={(courseId) =>
        void navigate({
          to: "/spaces/$courseId",
          params: { courseId },
          search: { tab: "overview" },
        })
      }
    />
  );
}
