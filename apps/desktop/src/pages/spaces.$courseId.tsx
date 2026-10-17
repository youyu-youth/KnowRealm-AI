import { createFileRoute } from "@tanstack/react-router";
import type { MasteryStatus } from "@/features/courses/api/types";
import { asCourseTab, type CourseTab } from "@/features/courses/courseTabs";
import { isMasteryStatus } from "@/features/courses/masteryStatus";
import { CourseDetailPage } from "@/features/courses/components/CourseDetailPage";

export const Route = createFileRoute("/spaces/$courseId")({
  validateSearch: (
    search: Record<string, unknown>,
  ): {
    tab: CourseTab;
    edit?: boolean;
    mastery?: MasteryStatus;
    planItem?: string;
  } => {
    const editing =
      search.edit === true || search.edit === "true" || search.edit === "1";
    const mastery = isMasteryStatus(search.mastery)
      ? search.mastery
      : undefined;
    return {
      tab: asCourseTab(search.tab),
      ...(editing ? { edit: true } : {}),
      ...(mastery ? { mastery } : {}),
      ...(typeof search.planItem === "string"
        ? { planItem: search.planItem }
        : {}),
    };
  },
  component: CourseDetailRoute,
});

export function CourseDetailRoute() {
  const { courseId } = Route.useParams();
  const { tab, edit, mastery, planItem } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CourseDetailPage
      courseId={courseId}
      tab={tab}
      initialEditing={edit}
      masteryStatus={mastery}
      planItemId={planItem}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/spaces/$courseId",
          search: {
            tab: nextTab,
            ...(mastery ? { mastery } : {}),
          },
          replace: true,
        })
      }
      onMasteryStatusChange={(next) =>
        void navigate({
          to: "/spaces/$courseId",
          search: {
            tab: "gps",
            ...(edit === true ? { edit: true } : {}),
            ...(next ? { mastery: next } : {}),
          },
          replace: true,
        })
      }
      onDeleted={() => navigate({ to: "/spaces" })}
    />
  );
}
