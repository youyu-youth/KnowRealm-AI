import { useQuery } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { learningPlanKeys } from "@/features/learningPlan/api/keys";
import { apiFetch } from "@/services/http/client";

export type RecordStudy = components["schemas"]["RecordStudyOut"];
export type StudyTab = RecordStudy["tab"];
export const studyKey = (itemId: string) =>
  [...learningPlanKeys.all, "study", itemId] as const;
const base = (itemId: string) => `/api/plan-items/${itemId}/study`;

export const studyApi = {
  state: (itemId: string, q = "") =>
    apiFetch<RecordStudy>(`${base(itemId)}?${new URLSearchParams({ q })}`),
  start: (itemId: string, body: components["schemas"]["RecordStudyStart"]) =>
    apiFetch<RecordStudy>(`${base(itemId)}/start`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  tab: (itemId: string, body: components["schemas"]["RecordStudyTabUpdate"]) =>
    apiFetch<RecordStudy>(`${base(itemId)}/tab`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

export function useRecordStudy(itemId?: string, q = "") {
  return useQuery({
    queryKey: [...studyKey(itemId ?? ""), q],
    // enabled 保证存在身份；可选值用于普通记录及课程入口不发计划学习请求。
    queryFn: () => studyApi.state(itemId as string, q),
    enabled: !!itemId,
    placeholderData: (previous) =>
      previous?.item.id === itemId ? previous : undefined,
    // 进入时重验访问身份及共享范围；窗口返回由记录学习页局部处理。
    refetchOnMount: "always",
  });
}
