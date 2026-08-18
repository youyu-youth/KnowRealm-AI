import { createFileRoute } from "@tanstack/react-router";
import { asCourseTab } from "@/features/courses/courseTabs";
import { CourseDetailPage } from "@/features/courses/components/CourseDetailPage";

export const Route = createFileRoute("/spaces/$courseId")({
  validateSearch: (search: Record<string, unknown>) => ({
    tab: asCourseTab(search.tab),
  }),
  component: CourseDetailRoute,
});

export function CourseDetailRoute() {
  const { courseId } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CourseDetailPage
      courseId={courseId}
      tab={tab}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/spaces/$courseId",
          search: { tab: nextTab },
          replace: true,
        })
      }
    />
  );
}
