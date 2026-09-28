import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type AgentRunOut = components["schemas"]["AgentRunOut"];
export type AgentRunDetailOut = components["schemas"]["AgentRunDetailOut"];
export type AgentOperationOut = components["schemas"]["AgentOperationOut"];
export type AgentActivityOut = components["schemas"]["AgentActivityOut"];
export type PurgeResultOut = components["schemas"]["PurgeResultOut"];

/** 任务状态分类（呈现与轮询共用；终态判定与后端 RUN_TERMINAL_STATUSES 对齐）。 */
export const RUN_TERMINAL_STATUSES = [
  "COMPLETED",
  "PARTIAL_COMPLETED",
  "FAILED",
  "CANCELLED",
] as const;

export function isRunActive(status: string | undefined): boolean {
  return (
    status !== undefined &&
    !(RUN_TERMINAL_STATUSES as readonly string[]).includes(status)
  );
}

/** 任务是否可显式唤醒（等待态；继续指令与失败项重试都只对等待态 / 部分完成有意义）。 */
export function isRunWaiting(status: string | undefined): boolean {
  return status === "WAITING_USER";
}

/** 可重试的步骤状态（与后端 AGENT_RUN_OPERATION_NOT_RETRYABLE 守卫一致）。 */
export function isStepRetryable(status: string): boolean {
  return status === "FAILED" || status === "SKIPPED";
}

/** 任务是否允许重试其失败步骤（与后端 _require_live_run 守卫同口径：
 * COMPLETED 与 CANCELLED 是终局，部分完成 / 失败任务重试会重开推进）。 */
export function canRetryRunSteps(status: string): boolean {
  return status !== "COMPLETED" && status !== "CANCELLED";
}

/** 任务状态 → 展示色（成功=强调绿、失败=警示红、未决/跳过=中性）。 */
export function runStatusTone(status: string): string {
  if (status === "SUCCEEDED" || status === "COMPLETED") {
    return "text-success-foreground";
  }
  if (status === "FAILED") {
    return "text-destructive";
  }
  return "text-muted-foreground";
}

/** 时间展示（本地时区）：操作 / 任务 / 审计行共用。 */
export function formatRunTime(iso: string | null): string {
  return iso === null ? "" : new Date(iso).toLocaleString();
}

/** 操作历史与任务推进 API（工单 01 查询 / 清理；工单 05 唤醒与取消）。
 * 唤醒仅由显式动作触发：继续（resumeRun）与失败项重试（retryRunOperation）
 * 都走原子抢占，取消（cancelRun）持久化后由推进每步检查。 */
export const operationHistoryApi = {
  listRuns: (params: { status?: string; session_id?: string } = {}) =>
    apiFetch<AgentRunOut[]>(`/api/agent/runs${buildQuery(params)}`),
  getRun: (runId: string) =>
    apiFetch<AgentRunDetailOut>(`/api/agent/runs/${encodeURIComponent(runId)}`),
  deleteRun: (runId: string) =>
    apiFetch<void>(`/api/agent/runs/${encodeURIComponent(runId)}`, {
      method: "DELETE",
    }),
  purgeFinished: () =>
    apiFetch<PurgeResultOut>("/api/agent/runs/purge-finished", {
      method: "POST",
    }),
  cancelRun: (runId: string) =>
    apiFetch<AgentRunOut>(
      `/api/agent/runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST" },
    ),
  resumeRun: (runId: string) =>
    apiFetch<AgentRunOut>(
      `/api/agent/runs/${encodeURIComponent(runId)}/resume`,
      { method: "POST" },
    ),
  retryRunOperation: (runId: string, operationId: string) =>
    apiFetch<AgentRunOut>(
      `/api/agent/runs/${encodeURIComponent(runId)}/operations/${encodeURIComponent(operationId)}/retry`,
      { method: "POST" },
    ),
  listOperations: (
    params: { status?: string; session_id?: string; limit?: number } = {},
  ) =>
    apiFetch<AgentOperationOut[]>(`/api/agent/operations${buildQuery(params)}`),
  listActivity: () => apiFetch<AgentActivityOut[]>("/api/agent/activity"),
};

function buildQuery(
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
