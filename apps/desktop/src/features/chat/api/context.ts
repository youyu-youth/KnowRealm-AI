import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export const contextApi = {
  changeRules: (
    sessionId: string,
    body: components["schemas"]["ContextRuleChange"],
  ) =>
    apiFetch<components["schemas"]["ContextRulesOut"]>(
      `/api/chat-sessions/${sessionId}/context/rules`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  history: (sessionId: string, offset: number, version: number) =>
    apiFetch<components["schemas"]["ContextHistoryOut"]>(
      `/api/chat-sessions/${sessionId}/context/history?offset=${offset}&expected_version=${version}`,
    ),
  changePin: (
    sessionId: string,
    body: components["schemas"]["ContextPinChange"],
  ) =>
    apiFetch<components["schemas"]["ContextPinsOut"]>(
      `/api/chat-sessions/${sessionId}/context/pins`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  search: (
    sessionId: string,
    body: components["schemas"]["ContextSearchRequest"],
  ) =>
    apiFetch<components["schemas"]["ContextSearchOut"]>(
      `/api/chat-sessions/${sessionId}/context/sources/search`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  read: (
    sessionId: string,
    body: components["schemas"]["ContextReadRequest"],
  ) =>
    apiFetch<components["schemas"]["ContextReadOut"]>(
      `/api/chat-sessions/${sessionId}/context/sources/read`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  get: (sessionId: string) =>
    apiFetch<components["schemas"]["ContextViewOut"]>(
      `/api/chat-sessions/${sessionId}/context`,
    ),
  preview: (
    sessionId: string,
    body: components["schemas"]["ContextPreviewRequest"],
  ) =>
    apiFetch<components["schemas"]["ContextViewOut"]>(
      `/api/chat-sessions/${sessionId}/context/estimates`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
