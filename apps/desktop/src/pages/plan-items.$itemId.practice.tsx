import { createFileRoute } from "@tanstack/react-router";
import { PracticePreparationPage } from "@/features/learningPlan/components/PracticePreparationPage";

export const Route = createFileRoute("/plan-items/$itemId/practice")({
  component: PracticePreparationRoute,
});

export function PracticePreparationRoute() {
  const { itemId } = Route.useParams();
  return <PracticePreparationPage itemId={itemId} />;
}
