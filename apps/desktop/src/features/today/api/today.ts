import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type TodaySummaryTodo = components["schemas"]["TodaySummaryTodoOut"];
export type TodayStats = components["schemas"]["TodayStatsOut"];
export type TodayTrendPoint = components["schemas"]["TodayTrendPointOut"];
export type TodayPlanItem = components["schemas"]["TodayPlanItemOut"];

export type TrendDays = 7 | 30;

export const todayApi = {
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
