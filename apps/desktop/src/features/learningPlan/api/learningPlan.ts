import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "@knowrealm/api-types";
import { learningPlanKeys } from "@/features/learningPlan/api/keys";
import { todayKeys } from "@/features/today/api/keys";
import { apiFetch } from "@/services/http/client";

export type LearningGoal = components["schemas"]["GoalOut"];
export type PlanVersion = components["schemas"]["PlanVersionOut"];
export type PlanDetail = components["schemas"]["PlanOut"];
export type PlanItem = components["schemas"]["PlanItemOut"];
export type PlanItemUpdateBody = components["schemas"]["PlanItemUpdate"];

export const learningPlanApi = {
  listGoals: (courseId: string) =>
    apiFetch<LearningGoal[]>(`/api/courses/${courseId}/goals`),
  listVersions: (courseId: string, goalId: string) =>
    apiFetch<PlanVersion[]>(`/api/courses/${courseId}/plans?goal_id=${goalId}`),
  plan: (courseId: string, planId: string) =>
    apiFetch<PlanDetail>(`/api/courses/${courseId}/plans/${planId}`),
  updateItem: (
    courseId: string,
    planId: string,
    itemId: string,
    body: PlanItemUpdateBody,
  ) =>
    apiFetch<PlanItem>(
      `/api/courses/${courseId}/plans/${planId}/items/${itemId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  completeItem: (courseId: string, planId: string, itemId: string) =>
    apiFetch<PlanItem>(
      `/api/courses/${courseId}/plans/${planId}/items/${itemId}/complete`,
      { method: "POST" },
    ),
  skipItem: (courseId: string, planId: string, itemId: string) =>
    apiFetch<PlanItem>(
      `/api/courses/${courseId}/plans/${planId}/items/${itemId}/skip`,
      { method: "POST" },
    ),
};

function useInvalidateLearningPlan() {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({ queryKey: learningPlanKeys.all });
}

export function useLearningGoals(courseId: string) {
  return useQuery({
    queryKey: learningPlanKeys.goals(courseId),
    queryFn: () => learningPlanApi.listGoals(courseId),
  });
}

export function usePlanVersions(courseId: string, goalId: string | null) {
  return useQuery({
    queryKey: learningPlanKeys.versions(courseId, goalId ?? ""),
    // enabled 已保证 goalId 非空（courseBrain.ts 同款收窄）。
    queryFn: () => learningPlanApi.listVersions(courseId, goalId as string),
    enabled: goalId != null,
  });
}

export function usePlanDetail(courseId: string, planId: string | null) {
  return useQuery({
    queryKey: learningPlanKeys.plan(courseId, planId ?? ""),
    // enabled 已保证 planId 非空（courseBrain.ts 同款收窄）。
    queryFn: () => learningPlanApi.plan(courseId, planId as string),
    enabled: planId != null,
  });
}

// 三项级写动作仅对当前生效版本可用（历史版本只读）；越权改历史版本由后端
// PLAN_VERSION_NOT_ACTIVE 拒绝，回执经 appToast 呈现（调用方负责）。
export function useUpdatePlanItem(courseId: string) {
  const invalidate = useInvalidateLearningPlan();
  return useMutation({
    mutationFn: ({
      planId,
      itemId,
      body,
    }: {
      planId: string;
      itemId: string;
      body: PlanItemUpdateBody;
    }) => learningPlanApi.updateItem(courseId, planId, itemId, body),
    onSuccess: invalidate,
  });
}

export function useCompletePlanItem() {
  const invalidate = useInvalidateLearningPlan();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      courseId,
      planId,
      itemId,
    }: {
      courseId: string;
      planId: string;
      itemId: string;
    }) => learningPlanApi.completeItem(courseId, planId, itemId),
    onSuccess: () => {
      invalidate();
      // 完成时间戳进入今日学习时长统计（工单 04）：今日页勾选后趋势/统计
      // 当场刷新上抬，不待重进页面。today/api/keys 无反向依赖、不构成环。
      void queryClient.invalidateQueries({ queryKey: todayKeys.all });
    },
  });
}

export function useSkipPlanItem(courseId: string) {
  const invalidate = useInvalidateLearningPlan();
  return useMutation({
    mutationFn: ({ planId, itemId }: { planId: string; itemId: string }) =>
      learningPlanApi.skipItem(courseId, planId, itemId),
    onSuccess: invalidate,
  });
}
