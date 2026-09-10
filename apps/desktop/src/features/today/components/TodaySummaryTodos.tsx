import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TodaySummaryTodo } from "@/features/today/api/today";

// 今日焦点卡内的真实区块：待确认总结有内容才出现（自带与示意清单的分隔线）；
// 读取中不渲染，失败给行内重试。样式执行卡内零 chrome（DESIGN.md §148）。
type TodaySummaryTodosProps = {
  data: TodaySummaryTodo[] | undefined;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
};

export function TodaySummaryTodos({
  data,
  isPending,
  isError,
  onRetry,
}: TodaySummaryTodosProps) {
  const { t } = useTranslation();

  if (isPending) {
    return (
      <p role="status" className="text-label text-ink-muted mt-4">
        {t("today.loading")}
      </p>
    );
  }

  if (isError) {
    return (
      <div role="alert" className="border-border-subtle mt-4 border-t pt-4">
        <h3 className="text-body-dense text-destructive font-medium">
          {t("today.errorTitle")}
        </h3>
        <p className="text-label text-ink-muted mt-1">
          {t("today.errorDescription")}
          <button
            type="button"
            className="text-ink ml-2 underline-offset-2 hover:underline"
            onClick={onRetry}
          >
            {t("today.retry")}
          </button>
        </p>
      </div>
    );
  }

  if (!data?.length) {
    return null;
  }

  return (
    <div className="border-border/60 mb-4 border-b pb-4">
      <h3 className="text-label text-ink-muted font-medium">
        {t("today.todoTitle")}
      </h3>
      <ul aria-label={t("today.todoListLabel")} className="mt-2 grid">
        {data.map((todo) => (
          <li key={todo.record_id} className="min-w-0">
            <Link
              to="/records/$recordId"
              params={{ recordId: todo.record_id }}
              className="hover:bg-surface-subtle focus-visible:ring-ring/40 group -mx-2 flex items-center justify-between gap-3 rounded-sm px-2 py-2 transition-colors focus-visible:ring-3"
            >
              <span className="min-w-0">
                <span
                  className="text-body text-ink block truncate font-medium"
                  title={todo.title}
                >
                  {todo.title}
                </span>
                <span className="text-label text-muted-foreground mt-0.5 block truncate">
                  {todo.course_name}
                </span>
              </span>
              <span className="text-label text-muted-foreground group-hover:text-ink inline-flex items-center gap-1 whitespace-nowrap transition-colors">
                {t("today.todoAction")}
                <ArrowRight
                  aria-hidden="true"
                  className="size-3.5 transition-transform group-hover:translate-x-0.5"
                />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
