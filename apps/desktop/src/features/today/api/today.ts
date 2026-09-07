import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type TodaySummaryTodo = components["schemas"]["TodaySummaryTodoOut"];
export type TodayStats = components["schemas"]["TodayStatsOut"];
export type TodayTrendPoint = components["schemas"]["TodayTrendPointOut"];

export type TrendDays = 7 | 30;

export const todayApi = {
  pendingSummaries: () =>
    apiFetch<TodaySummaryTodo[]>("/api/today/pending-summaries"),
  stats: () => apiFetch<TodayStats>("/api/today/stats"),
  // days 走后端白名单（7/30），插值无注入面。
  trend: (days: TrendDays) =>
    apiFetch<TodayTrendPoint[]>(`/api/today/stats/trend?days=${days}`),
};
