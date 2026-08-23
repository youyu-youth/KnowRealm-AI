import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type TodaySummaryTodo =
  components["schemas"]["TodaySummaryTodoOut"];

export const todayApi = {
  pendingSummaries: () =>
    apiFetch<TodaySummaryTodo[]>("/api/today/pending-summaries"),
};
