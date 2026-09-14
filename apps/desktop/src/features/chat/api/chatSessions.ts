import { createParser } from "eventsource-parser";
import type {
  ChatMessage,
  ChatRecordOption,
  ChatSession,
  ChatSessionCreate,
} from "@/features/chat/api/types";
import { apiErrorMessage } from "@/services/http/apiErrorMessage";
import {
  apiFetch,
  apiFetchNoContent,
  apiRequest,
} from "@/services/http/client";

export type ChatToolCallPayload = {
  tool: string;
  query: string;
};

export type ChatToolResultPayload = {
  tool: string;
  hits: number;
  ok: boolean;
};

export type ChatStreamHandlers = {
  onStatus: () => void;
  onToken: (text: string) => void;
  onToolCall: (payload: ChatToolCallPayload) => void;
  onToolResult: (payload: ChatToolResultPayload) => void;
  onDone: (payload: { messageId: string; content: string }) => void;
  onError: (payload: { code: string; detail: string }) => void;
};

/**
 * 发送消息并消费 SSE 回答流（POST 流 + eventsource-parser + AbortController）。
 * 非 2xx 由 apiRequest 统一抛 ApiError（如 409 在途 / 未配置供应商）。
 * webSearch=true 时本轮挂载联网搜索工具（后端无 key 时强制忽略该标志）。
 * 停止信号经 reader.cancel() 传导并在读结束时转抛 AbortError（不把 signal 交给
 * fetch：jsdom 测试环境的 AbortSignal 与 Node fetch 存在跨 realm 类型冲突）。
 */
async function streamMessage(
  sessionId: string,
  content: string,
  handlers: ChatStreamHandlers,
  signal: AbortSignal | undefined,
  webSearch = false,
): Promise<void> {
  if (signal?.aborted) throw abortError();
  const response = await apiRequest(
    `/api/chat-sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content, web_search: webSearch }),
      headers: { Accept: "text/event-stream" },
    },
  );
  // 传输层防御分支（FastAPI 流式 2xx 必有正文），与 abortError 同类：技术串、不走码表。
  if (!response.body) throw new Error("chat stream response has no body");
  const reader = response.body.getReader();
  const onAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", onAbort, { once: true });
  const parser = createParser({
    onEvent: (event) => {
      if (!event.event || !event.data) return;
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      const data: Record<string, unknown> =
        typeof payload === "object" && payload !== null
          ? (payload as Record<string, unknown>)
          : {};
      switch (event.event) {
        case "status":
          handlers.onStatus();
          break;
        case "token":
          if (typeof data.text === "string") handlers.onToken(data.text);
          break;
        case "tool_call":
          if (typeof data.tool === "string" && typeof data.query === "string") {
            handlers.onToolCall({ tool: data.tool, query: data.query });
          }
          break;
        case "tool_result":
          if (
            typeof data.tool === "string" &&
            typeof data.hits === "number" &&
            typeof data.ok === "boolean"
          ) {
            handlers.onToolResult({
              tool: data.tool,
              hits: data.hits,
              ok: data.ok,
            });
          }
          break;
        case "done":
          if (
            typeof data.message_id === "string" &&
            typeof data.content === "string"
          ) {
            handlers.onDone({
              messageId: data.message_id,
              content: data.content,
            });
          }
          break;
        case "error":
          if (
            typeof data.code === "string" &&
            typeof data.detail === "string"
          ) {
            // SSE 错误载荷经同一翻译入口（工单 04）：按码取译文，未命中回显中文原文；
            // params 按 ADR-0017 契约透传插值。
            const params =
              typeof data.params === "object" && data.params !== null
                ? (data.params as Record<string, unknown>)
                : undefined;
            handlers.onError({
              code: data.code,
              detail: apiErrorMessage(data.code, data.detail, params),
            });
          }
          break;
      }
    },
  });
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (signal?.aborted) throw abortError();
        break;
      }
      parser.feed(decoder.decode(value, { stream: true }));
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
  }
}

function abortError(): Error {
  const error = new Error("Aborted");
  error.name = "AbortError";
  return error;
}

export const chatApi = {
  list: () => apiFetch<ChatSession[]>("/api/chat-sessions"),
  recordOptions: () =>
    apiFetch<ChatRecordOption[]>("/api/chat-sessions/record-options"),
  create: (payload: ChatSessionCreate = { mode: "ASK" }) =>
    apiFetch<ChatSession>("/api/chat-sessions", {
      method: "POST",
      body: JSON.stringify(payload),
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
  getMessages: (sessionId: string) =>
    apiFetch<ChatMessage[]>(`/api/chat-sessions/${sessionId}/messages`),
  streamMessage,
};
