import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export const contextApi = {
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
