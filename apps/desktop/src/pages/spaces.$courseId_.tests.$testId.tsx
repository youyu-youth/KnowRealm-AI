import { createFileRoute } from "@tanstack/react-router";
import { asTestView, type TestView } from "@/features/quiz-tests/api/types";
import { QuizTestPage } from "@/features/quiz-tests/components/QuizTestPage";

export const Route = createFileRoute("/spaces/$courseId_/tests/$testId")({
  validateSearch: (
    search: Record<string, unknown>,
  ): { shortage?: number; view?: TestView } => {
    const shortage = Number(search.shortage);
    return {
      ...(Number.isInteger(shortage) && shortage > 0 ? { shortage } : {}),
      ...(search.view === undefined ? {} : { view: asTestView(search.view) }),
    };
  },
  component: QuizTestRoute,
});

export function QuizTestRoute() {
  const { courseId, testId } = Route.useParams();
  const { shortage, view } = Route.useSearch();
  return (
    <QuizTestPage
      courseId={courseId}
      testId={testId}
      shortage={shortage}
      view={view ?? "single"}
    />
  );
}
