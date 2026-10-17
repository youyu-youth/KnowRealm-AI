import { createFileRoute } from "@tanstack/react-router";
import { RecordStudyPage } from "@/features/learningPlan/components/RecordStudyPage";

export const Route = createFileRoute("/plan-items/$itemId/study")({
  component: RecordStudyRoute,
});

export function RecordStudyRoute() {
  const { itemId } = Route.useParams();
  return <RecordStudyPage key={itemId} itemId={itemId} />;
}
