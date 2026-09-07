import type { TrendDays } from "@/features/today/api/today";

export const todayKeys = {
  all: ["today"] as const,
  pendingSummaries: ["today", "pending-summaries"] as const,
  stats: ["today", "stats"] as const,
  trend: (days: TrendDays) => ["today", "stats-trend", days] as const,
};
