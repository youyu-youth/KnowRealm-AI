import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";
import type { LibraryItemsParams } from "@/features/library/api/library";

export const RECENT_MATERIALS_PARAMS = {
  order: "created",
  limit: 3,
} as const satisfies LibraryItemsParams;

export type TodaySummaryTodo = components["schemas"]["TodaySummaryTodoOut"];
export type TodayStats = components["schemas"]["TodayStatsOut"];
export type TodayTrendPoint = components["schemas"]["TodayTrendPointOut"];
export type TodayPlanItem = components["schemas"]["TodayPlanItemOut"];
export type TodayProgress = components["schemas"]["TodayProgressOut"];

export type TrendDays = 7 | 30;

export const todayApi = {
  progress: (course: string, order: "date" | "duration", page: number) => {
    const search = new URLSearchParams({
      order,
      offset: String((page - 1) * 20),
    });
    if (course !== "all") search.set("course_id", course);
    return apiFetch<TodayProgress>(`/api/today/progress?${search}`);
  },
  pendingSummaries: () =>
    apiFetch<TodaySummaryTodo[]>("/api/today/pending-summaries"),
  // 今日待学的计划项（跨空间，排期日 ≤ 今天且未完成）：勾选完成走
  // learningPlan 域的 useCompletePlanItem（与计划 Tab 同一写路径与缓存域）。
  planItems: () => apiFetch<TodayPlanItem[]>("/api/today/plan-items"),
  stats: () => apiFetch<TodayStats>("/api/today/stats"),
  // days 走后端白名单（7/30），插值无注入面。
  trend: (days: TrendDays) =>
    apiFetch<TodayTrendPoint[]>(`/api/today/stats/trend?days=${days}`),
};
