import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { todayKeys } from "@/features/today/api/keys";
import { todayApi } from "@/features/today/api/today";

export function TodaySummaryTodos() {
  const { t } = useTranslation();
  const todos = useQuery({
    queryKey: todayKeys.pendingSummaries,
    queryFn: todayApi.pendingSummaries,
  });

  if (todos.isPending) {
    return (
      <p
        role="status"
        className="text-body text-muted-foreground mt-8 flex items-center gap-2"
      >
        <Spinner aria-hidden="true" />
        {t("today.loading")}
      </p>
    );
  }

  if (todos.isError) {
    return (
      <section role="alert" className="border-border mt-8 border-t pt-8">
        <h2 className="text-section font-section text-ink">
          {t("today.errorTitle")}
        </h2>
        <p className="text-body text-muted-foreground mt-2">
          {t("today.errorDescription")}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          onClick={() => void todos.refetch()}
        >
          {t("today.retry")}
        </Button>
      </section>
    );
  }

  if (todos.data.length === 0) {
    return null;
  }

  return (
    <section className="border-border mt-8 border-t pt-8">
      <h2 className="text-section font-section text-ink">
        {t("today.todoTitle")}
      </h2>
      <ul aria-label={t("today.todoListLabel")} className="mt-3">
        {todos.data.map((todo) => (
          <li
            key={todo.record_id}
            className="border-border min-w-0 border-b last:border-b-0"
          >
            <Link
              to="/records/$recordId"
              params={{ recordId: todo.record_id }}
              className="hover:bg-surface-subtle focus-visible:ring-ring/40 -mx-2 grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-sm px-2 py-4 transition-colors focus-visible:ring-3"
            >
              <div className="min-w-0">
                <h3
                  className="text-body font-section text-ink truncate"
                  title={todo.title}
                >
                  {todo.title}
                </h3>
                <p className="text-label text-muted-foreground mt-1.5 truncate">
                  {todo.course_name}
                </p>
              </div>
              <span className="text-label text-muted-foreground whitespace-nowrap">
                {t("today.todoAction")}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
