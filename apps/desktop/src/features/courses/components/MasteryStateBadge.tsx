import { useTranslation } from "react-i18next";
import type { MasteryState } from "@/features/courses/courseDetailInsights";
import {
  masteryBadgeClassNames,
  masteryStateLabelKeys,
} from "@/features/courses/masteryState";
import { cn } from "@/lib/utils";

/** 掌握状态胶囊：已掌握（绿）/ 学习中（蓝）/ 未开始（灰）。 */
export function MasteryStateBadge({
  state,
  className,
}: {
  state: MasteryState;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "text-label font-label inline-flex h-6 items-center rounded-sm px-2 whitespace-nowrap",
        masteryBadgeClassNames[state],
        className,
      )}
    >
      {t(masteryStateLabelKeys[state])}
    </span>
  );
}
