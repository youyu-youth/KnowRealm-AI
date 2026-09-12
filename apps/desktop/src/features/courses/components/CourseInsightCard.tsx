import { ArrowRight, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { StatusTag } from "@/components/common/StatusTag";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockInsightSuggestions } from "@/features/courses/courseDetailInsights";

/** AI 助手 · 课程洞察：深色卡，建议内容为示意。 */
export function CourseInsightCard({
  course,
  onOpenChat,
}: {
  course: CourseDetail;
  onOpenChat: () => void;
}) {
  const { t } = useTranslation();
  const suggestions = useMemo(() => mockInsightSuggestions(course), [course]);

  return (
    <section className="bg-ink-strong text-paper dark:bg-surface-strong dark:text-ink-strong dark:border-border-subtle flex min-w-0 flex-col rounded-xl border border-transparent p-4">
      <header className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="size-4 shrink-0" aria-hidden="true" />
          <h2 className="text-section font-section min-w-0 truncate">
            {t("spaces.courseDetail.insight.title")}
          </h2>
        </div>
        <StatusTag className="bg-paper/10 text-paper dark:bg-surface-subtle dark:text-ink-muted shrink-0">
          {t("spaces.insights.sample")}
        </StatusTag>
      </header>
      <p className="text-label text-paper/70 dark:text-ink-muted mt-2">
        {t("spaces.courseDetail.insight.description")}
      </p>
      <ul className="mt-3 flex flex-col gap-2.5">
        {suggestions.map((suggestion) => (
          <li
            key={suggestion.key}
            className="text-body-dense flex gap-2 leading-relaxed"
          >
            <span
              aria-hidden="true"
              className="bg-paper/40 dark:bg-border-strong mt-1.5 size-1 shrink-0 rounded-full"
            />
            <span>
              {t(`spaces.courseDetail.insight.${suggestion.key}`, {
                percent: suggestion.percent,
                count: suggestion.count,
                chapter: suggestion.chapter
                  ? t(suggestion.chapter.nameKey)
                  : undefined,
              })}
            </span>
          </li>
        ))}
      </ul>
      <Button
        className="bg-paper text-ink-strong hover:bg-paper/90 dark:bg-primary dark:text-primary-foreground dark:hover:bg-primary-hover mt-4 w-full justify-between"
        onClick={onOpenChat}
      >
        {t("spaces.courseDetail.insight.cta")}
        <ArrowRight data-icon="inline-end" aria-hidden="true" />
      </Button>
    </section>
  );
}
