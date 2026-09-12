// 掌握状态的展示映射（示意掌握度域接入前的统一色板与文案 key）。
// 单色明度阶：mastered 最深 / learning 中性 / untouched 最浅，状态另有文字标签
// 与实心-空心差异，不依赖彩色（DESIGN.md §2.3）。
import { cssVar } from "@/charts/token";
import type { MasteryState } from "@/features/courses/courseDetailInsights";

export const masteryStateLabelKeys = {
  mastered: "spaces.courseDetail.mastery.mastered",
  learning: "spaces.courseDetail.mastery.learning",
  untouched: "spaces.courseDetail.mastery.untouched",
} satisfies Record<MasteryState, string>;

/** 图表状态色：读主题 token 的计算值，亮暗随 .dark 切换。 */
export function masteryChartColors(): Record<MasteryState, string | undefined> {
  return {
    mastered: cssVar("--ink-strong"),
    learning: cssVar("--ink-neutral"),
    untouched: cssVar("--ink-faint"),
  };
}

export const masteryDotClassNames = {
  mastered: "bg-ink-strong",
  learning: "bg-ink-muted",
  untouched: "bg-ink-faint",
} satisfies Record<MasteryState, string>;

export const masteryBadgeClassNames = {
  mastered: "bg-ink-strong text-paper",
  learning: "bg-surface-strong text-ink",
  untouched: "bg-surface-subtle text-muted-foreground",
} satisfies Record<MasteryState, string>;
