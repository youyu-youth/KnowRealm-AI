import type { components } from "@knowrealm/api-types";

export const chatKeys = {
  all: ["chat"] as const,
  sources: (
    sessionId: string,
    body: components["schemas"]["ContextSearchRequest"],
  ) => [...chatKeys.all, "sources", sessionId, body] as const,
  source: (
    sessionId: string,
    body: components["schemas"]["ContextReadRequest"],
  ) => [...chatKeys.all, "source", sessionId, body] as const,
  context: (
    sessionId: string,
    preview: components["schemas"]["ContextPreviewRequest"],
  ) => [...chatKeys.all, "context", sessionId, preview] as const,
  list: () => [...chatKeys.all, "list"] as const,
  recordOptions: () => [...chatKeys.all, "record-options"] as const,
  detail: (sessionId: string) =>
    [...chatKeys.all, "detail", sessionId] as const,
  messages: (sessionId: string) =>
    [...chatKeys.all, "messages", sessionId] as const,
};
