import { learningPlanKeys } from "@/features/learningPlan/api/keys";
import type { TrendDays } from "@/features/today/api/today";

export const todayKeys = {
  all: ["today"] as const,
  pendingSummaries: ["today", "pending-summaries"] as const,
  // 今日待学计划项的键挂在 learningPlan 域前缀下：计划 Tab 的完成/编辑/跳过
  // 写操作按该前缀失效缓存，今日页勾选与计划 Tab 状态自动保持一致（两侧均为
  // 纯键模块，互引不成环）。
  planItems: [...learningPlanKeys.all, "today-plan-items"] as const,
  stats: ["today", "stats"] as const,
  trend: (days: TrendDays) => ["today", "stats-trend", days] as const,
};
