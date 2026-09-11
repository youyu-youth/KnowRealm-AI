import { createFileRoute } from "@tanstack/react-router";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import { CourseDetailPage } from "@/features/courses/components/CourseDetailPage";

export const Route = createFileRoute("/spaces/$courseId")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { tab: CourseTab; edit?: boolean } => {
    const editing =
      search.edit === true || search.edit === "true" || search.edit === "1";
    return {
      tab: asCourseTab(search.tab),
      ...(editing ? { edit: true } : {}),
    };
  },
  component: CourseDetailRoute,
});

export function CourseDetailRoute() {
  const { courseId } = Route.useParams();
  const { tab, edit } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CourseDetailPage
      courseId={courseId}
      tab={tab}
      initialEditing={edit}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/spaces/$courseId",
          search: { tab: nextTab },
          replace: true,
        })
      }
      onDeleted={() => navigate({ to: "/spaces" })}
    />
  );
}
