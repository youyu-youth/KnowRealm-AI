import { createFileRoute } from "@tanstack/react-router";
import { QuizTestPage } from "@/features/quiz-tests/components/QuizTestPage";

export const Route = createFileRoute("/spaces/$courseId_/tests/$testId")({
  validateSearch: (search: Record<string, unknown>): { shortage?: number } => {
    const shortage = Number(search.shortage);
    return Number.isInteger(shortage) && shortage > 0 ? { shortage } : {};
  },
  component: QuizTestRoute,
});

export function QuizTestRoute() {
  const { courseId, testId } = Route.useParams();
  const { shortage } = Route.useSearch();
  return (
    <QuizTestPage courseId={courseId} testId={testId} shortage={shortage} />
  );
}
