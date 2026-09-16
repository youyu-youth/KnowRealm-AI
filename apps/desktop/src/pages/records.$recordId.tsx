import { createFileRoute } from "@tanstack/react-router";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";

type RecordDetailSearch = {
  tab?: "transcript" | "knowledge-points" | "quiz" | "review" | "todo";
  highlight?: string;
  segmentId?: string;
};

export const Route = createFileRoute("/records/$recordId")({
  validateSearch: (search: Record<string, unknown>): RecordDetailSearch => ({
    ...(search.tab === "transcript" ||
    search.tab === "knowledge-points" ||
    search.tab === "quiz" ||
    search.tab === "review" ||
    search.tab === "todo"
      ? { tab: search.tab }
      : {}),
    ...(typeof search.highlight === "string" && search.highlight
      ? { highlight: search.highlight }
      : {}),
    ...(typeof search.segmentId === "string" && search.segmentId
      ? { segmentId: search.segmentId }
      : {}),
  }),
  component: RecordDetailRoute,
});

export function RecordDetailRoute() {
  const { recordId } = Route.useParams();
  const { tab = "summary", highlight, segmentId } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <RecordDetailPage
      recordId={recordId}
      tab={tab}
      highlight={highlight}
      segmentId={segmentId}
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
