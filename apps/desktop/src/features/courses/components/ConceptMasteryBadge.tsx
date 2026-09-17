import { useTranslation } from "react-i18next";
import type { MasteryStatus } from "@/features/courses/api/types";
import {
  masteryStatusClassNames,
  masteryStatusLabelKeys,
} from "@/features/courses/masteryStatus";
import { cn } from "@/lib/utils";

/** 掌握状态胶囊：文字标签 + 色面，12px/520，4px 圆角（DESIGN.md §6 状态标签）。 */
export function ConceptMasteryBadge({
  status,
  className,
}: {
  status: MasteryStatus;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "text-label font-label inline-flex h-6 items-center rounded-xs px-2 whitespace-nowrap",
        masteryStatusClassNames[status],
        className,
      )}
    >
      {t(masteryStatusLabelKeys[status])}
    </span>
  );
}
