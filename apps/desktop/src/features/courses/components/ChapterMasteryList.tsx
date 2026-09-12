import { useTranslation } from "react-i18next";
import type { ChapterMastery } from "@/features/courses/courseDetailInsights";
import { MasteryStateBadge } from "@/features/courses/components/MasteryStateBadge";
import { masteryDotClassNames } from "@/features/courses/masteryState";
import { cn } from "@/lib/utils";

/** 章级掌握列表：概览卡与知识GPS 标签页共用。 */
export function ChapterMasteryList({
  chapters,
}: {
  chapters: ChapterMastery[];
}) {
  const { t } = useTranslation();
  return (
    <ol className="flex flex-col gap-3">
      {chapters.map((chapter) => (
        <li key={chapter.id} className="flex min-w-0 items-center gap-2.5">
          <span className="text-label text-ink-muted w-3.5 shrink-0 text-center tabular-nums">
            {chapter.index}
          </span>
          <span
            className="text-body-dense text-ink-strong w-24 shrink-0 truncate"
            title={t(chapter.nameKey)}
          >
            {t(chapter.nameKey)}
          </span>
          <div className="min-w-0 flex-1">
            <div
              role="progressbar"
              aria-label={t("spaces.courseDetail.gps.progressLabel", {
                chapter: chapter.index,
              })}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={chapter.percent}
              className="bg-surface-strong h-1.5 w-full overflow-hidden rounded-full"
            >
              <div
                className={cn(
                  "progress-reveal h-full rounded-full",
                  masteryDotClassNames[chapter.state],
                )}
                style={{ width: `${chapter.percent}%` }}
              />
            </div>
          </div>
          <span className="text-label text-ink-muted w-9 shrink-0 text-right tabular-nums">
            {chapter.percent}%
          </span>
          <MasteryStateBadge
            state={chapter.state}
            className="w-16 shrink-0 justify-center"
          />
        </li>
      ))}
    </ol>
  );
}
