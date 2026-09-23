import type { components } from "@knowrealm/api-types";
import { apiFetch, apiFetchNoContent } from "@/services/http/client";

export type AuthMode = components["schemas"]["AuthMode"];

/** 授权档位全集（三档；文案键按值拼接，见 i18n settings.operationHistory.authMode）。 */
export const AUTH_MODES = [
  "REQUEST_APPROVAL",
  "AUTO_APPROVE",
  "FULL_ACCESS",
] as const satisfies readonly AuthMode[];

export function isAuthMode(value: unknown): value is AuthMode {
  return (
    typeof value === "string" &&
    (AUTH_MODES as readonly string[]).includes(value)
  );
}

/** 授权档位 API（通用 Agent 第二阶段工单 02）：全局默认档读写（偏离项＋审计）
 * 与会话切档审计；会话档位本身按会话内存存前端（chatUiStore）。
 * 全局切换的 from 由后端自读 settings.json（审计权威口径），客户端只声明目标档。 */
export const agentAuthApi = {
  getAuthMode: () =>
    apiFetch<components["schemas"]["AgentAuthModeOut"]>("/api/agent/auth-mode"),
  putAuthMode: (to: AuthMode) =>
    apiFetch<components["schemas"]["AgentAuthModeOut"]>(
      "/api/agent/auth-mode",
      {
        method: "PUT",
        body: JSON.stringify({ to_mode: to }),
      },
    ),
  postSessionSwitch: (sessionId: string, from: AuthMode, to: AuthMode) =>
    // 端点 204 无响应体：apiFetch 会 .json() 解析空 body 抛
    // "Unexpected end of JSON input"，走 NoContent 变体（chatSessions.delete 先例）。
    apiFetchNoContent("/api/agent/auth-mode/sessions", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        from_mode: from,
        to_mode: to,
      }),
    }),
};

/** agent 域查询键：全局默认档与会话直执行回执（回执卡恢复链数据源）。 */
export const agentKeys = {
  authMode: ["agent", "auth-mode"] as const,
  sessionOperations: (sessionId: string) =>
    ["agent", "operations", sessionId] as const,
};
