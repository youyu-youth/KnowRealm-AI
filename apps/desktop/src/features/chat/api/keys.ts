export const chatKeys = {
  all: ["chat"] as const,
  context: (sessionId: string) =>
    [...chatKeys.all, "context", sessionId] as const,
  list: () => [...chatKeys.all, "list"] as const,
  recordOptions: () => [...chatKeys.all, "record-options"] as const,
  detail: (sessionId: string) =>
    [...chatKeys.all, "detail", sessionId] as const,
  messages: (sessionId: string) =>
    [...chatKeys.all, "messages", sessionId] as const,
};
