import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { components } from "@knowrealm/api-types";
import { sharedRefsKeys } from "@/features/sharedRefs/api/keys";
import { apiFetch, apiFetchNoContent } from "@/services/http/client";

export type SharedRef = components["schemas"]["SharedRefOut"];

export const sharedRefsApi = {
  list: (courseId: string) =>
    apiFetch<SharedRef[]>(`/api/courses/${courseId}/shared-refs`),
  add: (courseId: string, libraryItemId: string) =>
    apiFetch<SharedRef>(`/api/courses/${courseId}/shared-refs`, {
      method: "POST",
      body: JSON.stringify({ library_item_id: libraryItemId }),
    }),
  // 204 无响应体：走 NoContent 变体，避免空体 JSON 解析失败。
  remove: (courseId: string, libraryItemId: string) =>
    apiFetchNoContent(`/api/courses/${courseId}/shared-refs/${libraryItemId}`, {
      method: "DELETE",
    }),
};

function useInvalidateSharedRefs() {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({ queryKey: sharedRefsKeys.all });
}

export function useSharedRefs(courseId: string) {
  return useQuery({
    queryKey: sharedRefsKeys.list(courseId),
    queryFn: () => sharedRefsApi.list(courseId),
  });
}

export function useAddSharedRef(courseId: string) {
  const invalidate = useInvalidateSharedRefs();
  return useMutation({
    mutationFn: (libraryItemId: string) =>
      sharedRefsApi.add(courseId, libraryItemId),
    onSuccess: invalidate,
  });
}

export function useRemoveSharedRef(courseId: string) {
  const invalidate = useInvalidateSharedRefs();
  return useMutation({
    mutationFn: (libraryItemId: string) =>
      sharedRefsApi.remove(courseId, libraryItemId),
    onSuccess: invalidate,
  });
}
