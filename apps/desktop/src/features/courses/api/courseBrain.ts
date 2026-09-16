import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { courseBrainKeys } from "@/features/courses/api/keys";
import type {
  BrainApplyReviewRequest,
  BrainConceptCreate,
  BrainConceptListQuery,
  BrainConcept,
  BrainBuildAccepted,
  BrainSnapshot,
  ConceptSources,
} from "@/features/courses/api/types";
import { apiFetch } from "@/services/http/client";

export const courseBrainApi = {
  snapshot: (courseId: string) =>
    apiFetch<BrainSnapshot>(`/api/courses/${courseId}/brain`),
  triggerBuild: (courseId: string) =>
    apiFetch<BrainBuildAccepted>(`/api/courses/${courseId}/brain/builds`, {
      method: "POST",
    }),
  concepts: (courseId: string, query: BrainConceptListQuery = {}) => {
    const search = new URLSearchParams();
    if (query.status) search.set("status", query.status);
    if (query.limit != null) search.set("limit", String(query.limit));
    if (query.offset != null) search.set("offset", String(query.offset));
    return apiFetch<BrainConcept[]>(
      `/api/courses/${courseId}/brain/concepts${
        search.size > 0 ? `?${search}` : ""
      }`,
    );
  },
  sources: (courseId: string, conceptId: string) =>
    apiFetch<ConceptSources>(
      `/api/courses/${courseId}/brain/concepts/${conceptId}/sources`,
    ),
  createConcept: (courseId: string, payload: BrainConceptCreate) =>
    apiFetch<BrainConcept>(`/api/courses/${courseId}/brain/concepts`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  applyReview: (courseId: string, payload: BrainApplyReviewRequest) =>
    apiFetch<BrainSnapshot>(`/api/courses/${courseId}/brain/apply-review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// BUILDING 期间快照轮询节奏；其余状态不轮询（写操作与触发即时失效缓存）。
const SNAPSHOT_POLL_INTERVAL_MS = 2_000;

export function useCourseBrainSnapshot(courseId: string) {
  return useQuery({
    queryKey: courseBrainKeys.snapshot(courseId),
    queryFn: () => courseBrainApi.snapshot(courseId),
    refetchInterval: (query) =>
      query.state.data?.status === "BUILDING"
        ? SNAPSHOT_POLL_INTERVAL_MS
        : false,
  });
}

export function useCourseBrainConcepts(
  courseId: string,
  query: BrainConceptListQuery = {},
) {
  return useQuery({
    queryKey: courseBrainKeys.concepts(courseId, query),
    queryFn: () => courseBrainApi.concepts(courseId, query),
  });
}

export function useConceptSources(courseId: string, conceptId: string | null) {
  return useQuery({
    queryKey: courseBrainKeys.sources(courseId, conceptId),
    // enabled 已保证 conceptId 非空。
    queryFn: () => courseBrainApi.sources(courseId, conceptId as string),
    enabled: conceptId != null,
  });
}

// 写操作统一失效整个 brain 域：confirm/merge 会同时改变快照计数、图谱、
// 概念列表与来源链接（merge 迁移锚点），按前缀失效比逐键枚举更不易漏。
function useInvalidateBrain() {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({ queryKey: courseBrainKeys.all });
}

export function useTriggerBuild(courseId: string) {
  const invalidate = useInvalidateBrain();
  return useMutation({
    mutationFn: () => courseBrainApi.triggerBuild(courseId),
    onSuccess: invalidate,
  });
}

export function useApplyReview(courseId: string) {
  const invalidate = useInvalidateBrain();
  return useMutation({
    mutationFn: (payload: BrainApplyReviewRequest) =>
      courseBrainApi.applyReview(courseId, payload),
    onSuccess: invalidate,
  });
}

export function useCreateConcept(courseId: string) {
  const invalidate = useInvalidateBrain();
  return useMutation({
    mutationFn: (payload: BrainConceptCreate) =>
      courseBrainApi.createConcept(courseId, payload),
    onSuccess: invalidate,
  });
}

export type CourseBrainPhase = BrainSnapshot["status"];

/**
 * 快照查询态 + 后端六态（EMPTY/BUILDING/REVIEW/READY/STALE/FAILED）归一成
 * 判别联合：页面按 phase 穷尽分支渲染状态栏/空态引导/图谱，不再各自判空。
 */
export type CourseBrainView =
  | { phase: "loading" }
  | { phase: "error" }
  | { phase: CourseBrainPhase; snapshot: BrainSnapshot };

export function useCourseBrainView(courseId: string): CourseBrainView {
  const snapshot = useCourseBrainSnapshot(courseId);
  if (snapshot.isPending) return { phase: "loading" };
  if (snapshot.isError) return { phase: "error" };
  return { phase: snapshot.data.status, snapshot: snapshot.data };
}
