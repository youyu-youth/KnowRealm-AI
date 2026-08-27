import { createFileRoute } from "@tanstack/react-router";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";

type RecordDetailSearch = {
  tab?: "transcript" | "knowledge-points" | "quiz" | "todo";
};

export const Route = createFileRoute("/records/$recordId")({
  validateSearch: (search: Record<string, unknown>): RecordDetailSearch => ({
    ...(search.tab === "transcript" ||
    search.tab === "knowledge-points" ||
    search.tab === "quiz" ||
    search.tab === "todo"
      ? { tab: search.tab }
      : {}),
  }),
  component: RecordDetailRoute,
});

export function RecordDetailRoute() {
  const { recordId } = Route.useParams();
  const { tab = "summary" } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <RecordDetailPage
      recordId={recordId}
      tab={tab}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/records/$recordId",
          search: {
            tab: nextTab === "summary" ? undefined : nextTab,
          },
          replace: true,
        })
      }
      onDeleted={(courseId) =>
        courseId
          ? navigate({
              to: "/spaces/$courseId",
              params: { courseId },
              search: { tab: "records" },
            })
          : navigate({ to: "/inbox" })
      }
    />
  );
}
