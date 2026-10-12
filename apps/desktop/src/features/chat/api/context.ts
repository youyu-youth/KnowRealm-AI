import type { components } from "@knowrealm/api-types";
import { apiFetch } from "@/services/http/client";

export const contextApi = {
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
