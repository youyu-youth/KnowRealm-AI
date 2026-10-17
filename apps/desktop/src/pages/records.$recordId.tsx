import { createFileRoute } from "@tanstack/react-router";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";
import { RecordStudySession } from "@/features/learningPlan/components/RecordStudySession";

type RecordDetailSearch = {
  tab?: "transcript" | "knowledge-points" | "quiz" | "review" | "todo";
  highlight?: string;
  segmentId?: string;
  studyItem?: string;
  studyVisit?: string;
};

export const Route = createFileRoute("/records/$recordId")({
  validateSearch: (search: Record<string, unknown>): RecordDetailSearch => ({
    ...(typeof search.studyItem === "string" &&
    typeof search.studyVisit === "string"
      ? { studyItem: search.studyItem, studyVisit: search.studyVisit }
      : {}),
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
  const {
    tab = "summary",
    highlight,
    segmentId,
    studyItem,
    studyVisit,
  } = Route.useSearch();
  const navigate = Route.useNavigate();
  if (studyItem && studyVisit)
    return (
      <RecordStudySession
        key={`${studyItem}-${studyVisit}`}
        itemId={studyItem}
        visitId={studyVisit}
        recordId={recordId}
        tab={tab}
        onTabChange={(nextTab) =>
          void navigate({
            to: "/records/$recordId",
            search: {
              tab: nextTab === "summary" ? undefined : nextTab,
              studyItem,
              studyVisit,
            },
            replace: true,
          })
        }
      />
    );
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
