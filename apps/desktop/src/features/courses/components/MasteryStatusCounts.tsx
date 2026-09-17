import { useTranslation } from "react-i18next";
import type { CourseMastery } from "@/features/courses/api/types";
import {
  masteryDotClassNames,
  masteryStatusCountKeys,
  masteryStatusLabelKeys,
  masteryStatuses,
} from "@/features/courses/masteryStatus";
import { cn } from "@/lib/utils";

/** 四类掌握状态计数（状态点 + 数字 + 文案）：概览卡与知识GPS 标签页共用。 */
export function MasteryStatusCounts({
  counts,
  className,
  itemClassName,
  valueClassName,
}: {
  counts: CourseMastery["status_counts"];
  className?: string;
  itemClassName?: string;
  valueClassName?: string;
}) {
  const { t } = useTranslation();
  return (
    <dl className={cn("min-w-0", className)}>
      {masteryStatuses.map((status) => (
        <div
          key={status}
          className={cn("flex min-w-0 items-center gap-1.5", itemClassName)}
        >
          <span
            aria-hidden="true"
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              masteryDotClassNames[status],
            )}
          />
          <dd
            className={cn(
              "text-body-dense text-ink-strong tabular-nums",
              valueClassName,
            )}
          >
            {counts[masteryStatusCountKeys[status]]}
          </dd>
          <dt className="text-label text-ink-muted truncate">
            {t(masteryStatusLabelKeys[status])}
          </dt>
        </div>
      ))}
    </dl>
  );
}
