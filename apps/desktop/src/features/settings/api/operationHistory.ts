import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export type AgentRunOut = components["schemas"]["AgentRunOut"];
export type AgentRunDetailOut = components["schemas"]["AgentRunDetailOut"];
export type AgentOperationOut = components["schemas"]["AgentOperationOut"];
export type AgentActivityOut = components["schemas"]["AgentActivityOut"];
export type PurgeResultOut = components["schemas"]["PurgeResultOut"];

/** 操作历史（通用 Agent 第二阶段工单 01）：runs / operations / activity 查询
 * 与显式清理；Run 推进与模式切换审计随 02/05 票接入，本阶段 runs 恒空态。 */
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
  listOperations: (params: { status?: string } = {}) =>
    apiFetch<AgentOperationOut[]>(`/api/agent/operations${buildQuery(params)}`),
  listActivity: () => apiFetch<AgentActivityOut[]>("/api/agent/activity"),
};

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
