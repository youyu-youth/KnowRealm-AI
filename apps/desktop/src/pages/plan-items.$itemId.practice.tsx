import { createFileRoute } from "@tanstack/react-router";
import { PracticePreparationPage } from "@/features/learningPlan/components/PracticePreparationPage";

export const Route = createFileRoute("/plan-items/$itemId/practice")({
  validateSearch: (search: Record<string, unknown>): { round?: string } => ({
    round: typeof search.round === "string" ? search.round : undefined,
  }),
  component: PracticePreparationRoute,
});

export function PracticePreparationRoute() {
  const { itemId } = Route.useParams();
  const { round } = Route.useSearch();
  return <PracticePreparationPage itemId={itemId} selectedRoundId={round} />;
}
