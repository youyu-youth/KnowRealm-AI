import { appToast } from "@/components/common/appToastManager";
import { ApiError } from "@/services/http/client";

/** 计划项写动作失败回执（计划 Tab 与今日页双源共用）：后端错误码文案优先，
 * 无码回退调用方给的场景文案。 */
export function toastMutationError(error: unknown, fallback: string) {
  appToast.add({
    description:
      error instanceof ApiError && error.message ? error.message : fallback,
  });
}
