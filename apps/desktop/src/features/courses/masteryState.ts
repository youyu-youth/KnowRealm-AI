// 掌握状态的展示映射（示意掌握度域接入前的统一色板与文案 key）。
import type { MasteryState } from "@/features/courses/courseDetailInsights";

export const masteryStateLabelKeys = {
  mastered: "spaces.courseDetail.mastery.mastered",
  learning: "spaces.courseDetail.mastery.learning",
  untouched: "spaces.courseDetail.mastery.untouched",
} satisfies Record<MasteryState, string>;

/** 图表状态色：与图例圆点、徽章保持同一套视觉（亮暗主题通用）。 */
export const masteryChartColors = {
  mastered: "#10b981",
  learning: "#3b82f6",
  untouched: "#9aa1ac",
} satisfies Record<MasteryState, string>;

export const masteryDotClassNames = {
  mastered: "bg-emerald-500",
  learning: "bg-blue-500",
  untouched: "bg-ink-faint",
} satisfies Record<MasteryState, string>;

export const masteryBadgeClassNames = {
  mastered:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/45 dark:text-emerald-300",
  learning: "bg-blue-50 text-blue-700 dark:bg-blue-950/45 dark:text-blue-300",
  untouched: "bg-surface-subtle text-muted-foreground",
} satisfies Record<MasteryState, string>;
