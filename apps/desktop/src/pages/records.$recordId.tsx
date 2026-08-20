import { createFileRoute } from "@tanstack/react-router";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";

type RecordDetailSearch = {
  tab?: "transcript";
  jobId?: string;
};

export const Route = createFileRoute("/records/$recordId")({
  validateSearch: (search: Record<string, unknown>): RecordDetailSearch => ({
    ...(search.tab === "transcript" ? { tab: "transcript" } : {}),
    ...(typeof search.jobId === "string" ? { jobId: search.jobId } : {}),
  }),
  component: RecordDetailRoute,
});

export function RecordDetailRoute() {
  const { recordId } = Route.useParams();
  const { tab = "summary", jobId } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <RecordDetailPage
      recordId={recordId}
      tab={tab}
      jobId={jobId}
      onTabChange={(nextTab) =>
        void navigate({
          to: "/records/$recordId",
          search: {
            tab: nextTab === "transcript" ? "transcript" : undefined,
            jobId,
          },
          replace: true,
        })
      }
      onDeleted={(courseId) =>
        navigate({
          to: "/spaces/$courseId",
          params: { courseId },
          search: { tab: "records" },
        })
      }
    />
  );
}
