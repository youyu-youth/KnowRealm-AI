import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { quizTestKeys } from "@/features/quiz-tests/api/keys";
import { quizTestApi } from "@/features/quiz-tests/api/quizTests";
import { QUIZ_QUESTION_TYPES } from "@/features/quiz-tests/api/types";

export function QuizTestPage({
  courseId,
  testId,
  shortage,
}: {
  courseId: string;
  testId: string;
  shortage?: number;
}) {
  const { t } = useTranslation();
  const test = useQuery({
    queryKey: quizTestKeys.detail(testId),
    queryFn: () => quizTestApi.get(testId),
  });

  if (test.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground flex items-center gap-2 p-8"
      >
        <Spinner aria-hidden="true" />
        {t("spaces.simulations.paper.loading")}
      </p>
    );
  }

  if (test.isError) {
    return (
      <section role="alert" className="max-w-workbench px-content mx-auto py-8">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("spaces.simulations.paper.errorTitle")}
        </h1>
        <Button
          variant="outline"
          className="mt-6"
          onClick={() => void test.refetch()}
        >
          {t("spaces.simulations.retry")}
        </Button>
      </section>
    );
  }

  return (
    <section className="work-surface-enter max-w-workbench px-content mx-auto py-8">
      <Link
        to="/spaces/$courseId"
        params={{ courseId }}
        search={{ tab: "tests" }}
        className="text-body text-muted-foreground hover:text-ink-strong focus-visible:ring-ring/40 -ml-1 flex w-fit items-center gap-1.5 rounded-sm focus-visible:ring-3"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t("spaces.simulations.paper.back")}
      </Link>
      <header className="mt-5 border-b pb-6">
        <h1 className="text-headline font-headline text-ink-strong">
          {t("spaces.simulations.paper.title")}
        </h1>
        <p className="text-body text-muted-foreground mt-2">
          {t("spaces.simulations.paper.description", {
            count: test.data.total_count,
          })}
        </p>
        {shortage ? (
          <p
            role="status"
            className="bg-warning-soft text-warning-foreground text-body mt-4 px-3 py-2"
          >
            {t("spaces.simulations.paper.shortage", { count: shortage })}
          </p>
        ) : null}
      </header>

      {QUIZ_QUESTION_TYPES.map((type) => {
        const items = test.data.items.filter(
          (item) => item.question_type === type,
        );
        if (items.length === 0) return null;
        return (
          <section key={type} className="mt-8">
            <h2 className="text-section font-section text-ink">
              {t(`record.detail.quiz.type.${type}`)}
            </h2>
            <ol className="mt-3">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="border-border border-t py-5 first:border-t-0"
                >
                  <p className="text-body text-ink">
                    <span className="text-muted-foreground mr-2 tabular-nums">
                      {item.sequence_no}.
                    </span>
                    {item.stem}
                  </p>
                  {item.options.length > 0 ? (
                    <ol className="text-body text-muted-foreground mt-3 grid gap-2 pl-7">
                      {item.options.map((option, index) => (
                        <li key={`${item.id}-${index}`}>
                          {String.fromCharCode(65 + index)}. {option}
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
        );
      })}
    </section>
  );
}
