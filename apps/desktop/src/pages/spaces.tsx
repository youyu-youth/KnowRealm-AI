import { createFileRoute } from "@tanstack/react-router";
import type {
  CourseListQuery,
  CourseType,
  EducationStage,
} from "@/features/courses/api/types";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
import {
  courseTypeLabelKeys,
  educationStageLabelKeys,
} from "@/features/courses/courseOptions";

function isEducationStage(value: unknown): value is EducationStage {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(educationStageLabelKeys, value)
  );
}

function isCourseType(value: unknown): value is CourseType {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(courseTypeLabelKeys, value)
  );
}

export const Route = createFileRoute("/spaces")({
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
    />
  );
}
