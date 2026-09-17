// 掌握状态与 Confidence 的展示映射（真实 Mastery 域）：
// 单色明度阶为主，颜色只作为辅助语义（DESIGN.md §2.3），状态必须同时有文字标签。

import type {
  CourseMastery,
  MasteryConfidence,
  MasteryStatus,
} from "@/features/courses/api/types";

export const masteryStatuses: MasteryStatus[] = [
  "NOT_ENOUGH_DATA",
  "WEAK",
  "LEARNING",
  "STABLE",
];

const masteryStatusSet: ReadonlySet<string> = new Set(masteryStatuses);

export function isMasteryStatus(value: unknown): value is MasteryStatus {
  return typeof value === "string" && masteryStatusSet.has(value);
}

/** 状态 → 课程分布计数字段名（API 返回 snake_case）。 */
export const masteryStatusCountKeys: Record<
  MasteryStatus,
  keyof CourseMastery["status_counts"]
> = {
  NOT_ENOUGH_DATA: "not_enough_data",
  WEAK: "weak",
  LEARNING: "learning",
  STABLE: "stable",
};

export const masteryStatusLabelKeys: Record<MasteryStatus, string> = {
  NOT_ENOUGH_DATA: "spaces.courseDetail.mastery.NOT_ENOUGH_DATA",
  WEAK: "spaces.courseDetail.mastery.WEAK",
  LEARNING: "spaces.courseDetail.mastery.LEARNING",
  STABLE: "spaces.courseDetail.mastery.STABLE",
};

export const masteryStatusClassNames: Record<MasteryStatus, string> = {
  NOT_ENOUGH_DATA: "bg-surface-subtle text-ink-muted",
  WEAK: "bg-warning-soft text-warning-foreground",
  LEARNING: "bg-surface-strong text-ink",
  STABLE: "bg-success-soft text-success-foreground",
};

export const masteryDotClassNames: Record<MasteryStatus, string> = {
  NOT_ENOUGH_DATA: "bg-ink-faint",
  WEAK: "bg-warning-foreground",
  LEARNING: "bg-ink-muted",
  STABLE: "bg-success-foreground",
};

export const masteryConfidenceLabelKeys: Record<MasteryConfidence, string> = {
  LOW: "spaces.courseDetail.mastery.confidence.LOW",
  MEDIUM: "spaces.courseDetail.mastery.confidence.MEDIUM",
  HIGH: "spaces.courseDetail.mastery.confidence.HIGH",
};

/** 分数 → 整数百分比；数据不足为 null，不把「尚未计算」伪装成 0%。 */
export function masteryPercentOf(
  score: number | null | undefined,
): number | null {
  return score === null || score === undefined ? null : Math.round(score * 100);
}
