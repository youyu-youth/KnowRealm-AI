import { createFileRoute } from "@tanstack/react-router";
import { RecordDetailPage } from "@/features/records/components/RecordDetailPage";

export const Route = createFileRoute("/records/$recordId")({
  component: RecordDetailRoute,
});

export function RecordDetailRoute() {
  const { recordId } = Route.useParams();
  return <RecordDetailPage recordId={recordId} />;
}
