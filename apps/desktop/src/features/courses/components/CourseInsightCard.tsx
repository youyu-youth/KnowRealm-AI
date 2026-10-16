import { Sparkles } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { SurfaceCard } from "@/components/common/SurfaceCard";
import { Button } from "@/components/ui/button";
import type { CourseDetail } from "@/features/courses/api/types";
import { mockInsightSuggestions } from "@/features/courses/courseDetailInsights";

/** AI 助手 · 课程洞察：与普通内容同一表面材料，建议内容为示意。 */
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
    <SurfaceCard
      title={
        <span className="flex min-w-0 items-center gap-1.5">
          <Sparkles
            className="text-ink-muted size-4 shrink-0"
            aria-hidden="true"
          />
          <span className="min-w-0 truncate">
            {t("spaces.courseDetail.insight.title")}
          </span>
        </span>
      }
      sample
      className="course-overview-section course-insight"
    >
      <ul className="mt-3 flex flex-col gap-2.5">
        {suggestions.map((suggestion) => (
          <li
            key={suggestion.key}
            className="text-body-dense flex gap-2 leading-relaxed"
          >
            <span
              aria-hidden="true"
              className="bg-ink-faint mt-1.5 size-1 shrink-0 rounded-full"
            />
            <span>
              {t(`spaces.courseDetail.insight.${suggestion.key}`, {
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
        variant="ghost"
        size="sm"
        className="course-insight-action mt-3"
        onClick={onOpenChat}
      >
        {t("spaces.courseDetail.insight.cta")}
      </Button>
    </SurfaceCard>
  );
}
