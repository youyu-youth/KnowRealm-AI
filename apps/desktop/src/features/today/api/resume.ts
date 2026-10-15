import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { components } from "@knowrealm/api-types";
import { todayKeys } from "@/features/today/api/keys";
import { apiFetch, apiFetchNoContent } from "@/services/http/client";
import { isRestartPending } from "@/services/restartPending";

export type LearningResume = components["schemas"]["LearningResumeOut"];
export type LearningVisit = components["schemas"]["LearningResumeUpdate"];

export const resumeApi = {
  list: () =>
    apiFetch<LearningResume[]>("/api/today/continue-learning?limit=3"),
};

type ResumeAction =
  | { action: "visit"; visit: LearningVisit }
  | { action: "remove"; kind: LearningResume["kind"]; target_id: string }
  | { action: "clear" };

export function useLearningResumeActions() {
  const queryClient = useQueryClient();
  return useMutation({
    // 同一 QueryClient 的访问、移除、清空串行，清空不会被在途访问写回。
    scope: { id: "learning-resume" },
    mutationFn: async (action: ResumeAction) => {
      if (isRestartPending()) throw new Error("RESTART_REQUIRED");
      if (action.action === "visit") {
        await apiFetchNoContent("/api/today/continue-learning", {
          method: "PUT",
          body: JSON.stringify(action.visit),
        });
      } else {
        const path =
          action.action === "clear"
            ? "/api/today/continue-learning"
            : `/api/today/continue-learning/${action.kind}/${encodeURIComponent(action.target_id)}`;
        await apiFetchNoContent(path, { method: "DELETE" });
      }
    },
    onSuccess: async () => {
      await queryClient.cancelQueries({ queryKey: todayKeys.continueLearning });
      await queryClient.invalidateQueries({
        queryKey: todayKeys.continueLearning,
      });
    },
  });
}
