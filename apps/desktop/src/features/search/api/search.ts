import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type SearchOut = components["schemas"]["SearchOut"];
export type SearchCourseItem = components["schemas"]["SearchCourseItem"];
export type SearchRecordItem = components["schemas"]["SearchRecordItem"];
export type SearchKnowledgePointItem =
  components["schemas"]["SearchKnowledgePointItem"];

export const searchApi = {
  // limit 省略时后端默认每类 5 条；资产库视图（04）传更大值。
  search: (q: string, limit?: number) => {
    const params = new URLSearchParams({ q });
    if (limit !== undefined) params.set("limit", String(limit));
    return apiFetch<SearchOut>(`/api/search?${params.toString()}`);
  },
};
