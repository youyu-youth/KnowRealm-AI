import { createFileRoute } from "@tanstack/react-router";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
import {
  isCourseStatus,
  isCourseType,
  isEducationStage,
  isLearningContext,
} from "@/features/courses/courseOptions";
import {
  isSpacesSort,
  isSpacesView,
  type SpacesSearch,
} from "@/features/courses/spacesSearch";

export const Route = createFileRoute("/spaces/")({
  validateSearch: (search): SpacesSearch => {
    const q = typeof search.q === "string" ? search.q.trim() : "";
    return {
      q: q.length > 0 && q.length <= 100 ? q : undefined,
      learning_context: isLearningContext(search.learning_context)
        ? search.learning_context
        : undefined,
      status: isCourseStatus(search.status) ? search.status : undefined,
      sort: isSpacesSort(search.sort) ? search.sort : undefined,
      view: isSpacesView(search.view) ? search.view : undefined,
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
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CoursesPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
      onOpenCourse={(courseId) =>
        void navigate({
          to: "/spaces/$courseId",
          params: { courseId },
          search: { tab: "overview" },
        })
      }
      onEditCourse={(courseId) =>
        void navigate({
          to: "/spaces/$courseId",
          params: { courseId },
          search: { tab: "overview", edit: true },
        })
      }
    />
  );
}
