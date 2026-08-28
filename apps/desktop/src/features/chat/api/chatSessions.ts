import { apiFetch, apiFetchNoContent } from "@/services/http/client";
import type { ChatSession } from "@/features/chat/api/types";

export const chatApi = {
  list: () => apiFetch<ChatSession[]>("/api/chat-sessions"),
  create: () =>
    apiFetch<ChatSession>("/api/chat-sessions", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  get: (sessionId: string) =>
    apiFetch<ChatSession>(`/api/chat-sessions/${sessionId}`),
  rename: (sessionId: string, title: string) =>
    apiFetch<ChatSession>(`/api/chat-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  delete: (sessionId: string) =>
    apiFetchNoContent(`/api/chat-sessions/${sessionId}`, { method: "DELETE" }),
};
