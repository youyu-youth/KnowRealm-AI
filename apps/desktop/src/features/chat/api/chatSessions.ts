import { createParser } from "eventsource-parser";
import { z } from "zod";
import type { AuthMode } from "@/features/agent/api/authMode";
import type {
  ChatKnowledgePointSaveRequest,
  ChatMessage,
  ChatPageSnapshot,
  ChatRecordOption,
  ChatResponseProcess,
  ChatSession,
  ChatSessionCreate,
  KnowledgePointOut,
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
  toolCallId?: string;
  segmentId?: string;
  process?: ChatResponseProcess;
};

export type ChatToolResultPayload = {
  tool: string;
  hits: number;
  ok: boolean;
  toolCallId?: string;
  process?: ChatResponseProcess;
};

/** 模型经 propose_memory 创建的待确认记忆提案（工单 06，done 载荷透传）。 */
export type ChatMemoryProposalPayload = {
  proposalId: string;
  items: string[];
};

/** 模型经 propose_ingest 创建的待确认入库提案（研究会话 V1，done 载荷透传）。 */
export type ChatResearchProposalPayload = {
  proposalId: string;
  url: string;
  title: string;
};

export type ChatDonePayload = {
  messageId: string;
  content: string;
  process?: ChatResponseProcess;
  /** 本轮实际注入的学习者记忆条目（未注入时缺省）。 */
  memoryUsed?: string[];
  /** 本轮新建的 MEMORY 提案（无时缺省）。 */
  memoryProposals?: ChatMemoryProposalPayload[];
  /** 本轮新建的 RESEARCH_INGEST 入库提案（无时缺省，研究会话）。 */
  researchProposals?: ChatResearchProposalPayload[];
};

/**
 * done 载荷的可选扩展字段（工单 06 / 研究会话 V1）：本轮注入记忆与新建提案
 * （记忆 + 入库）。载荷来自后端 JSON，字段形态经防御性收窄，缺省即 undefined
 * （安全省略）；形状不符的提案静默跳过。直执行回执不在此解析——回执卡以
 * assistant 行持久锚点 + operation 查询为事实源（工单 02 P2 修复）。
 */
function parseTurnProposalFields(data: Record<string, unknown>): {
  memoryUsed?: string[];
  memoryProposals?: ChatMemoryProposalPayload[];
  researchProposals?: ChatResearchProposalPayload[];
} {
  // 源字段缺席时键省略（缺省即 undefined，向后兼容旧载荷）。
  const memoryUsed = Array.isArray(data.memory_used)
    ? data.memory_used.filter(
        (item): item is string => typeof item === "string",
      )
    : undefined;
  const memoryProposals = parseProposalList(data.memory_proposals, (raw) =>
    typeof raw.proposal_id === "string" && Array.isArray(raw.items)
      ? [
          {
            proposalId: raw.proposal_id,
            items: raw.items.filter(
              (entry): entry is string => typeof entry === "string",
            ),
          },
        ]
      : [],
  );
  const researchProposals = parseProposalList(data.research_proposals, (raw) =>
    typeof raw.proposal_id === "string" &&
    typeof raw.url === "string" &&
    typeof raw.title === "string"
      ? [{ proposalId: raw.proposal_id, url: raw.url, title: raw.title }]
      : [],
  );
  return {
    ...(memoryUsed !== undefined ? { memoryUsed } : {}),
    ...(Array.isArray(data.memory_proposals) ? { memoryProposals } : {}),
    ...(Array.isArray(data.research_proposals) ? { researchProposals } : {}),
  };
}

function parseProposalList<T>(
  value: unknown,
  toPayload: (raw: Record<string, unknown>) => T[],
): T[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item): T[] => {
    if (typeof item !== "object" || item === null) return [];
    return toPayload(item as Record<string, unknown>);
  });
}

const processSchema: z.ZodType<ChatResponseProcess> = z.object({
  id: z.string(),
  session_id: z.string(),
  user_message_id: z.string(),
  assistant_message_id: z.string().nullable(),
  status: z.enum(["RUNNING", "COMPLETED", "FAILED", "INTERRUPTED"]),
  started_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
  ended_at: z.string().datetime({ offset: true }).nullable(),
  elapsed_ms: z.number().int().nonnegative(),
  history_saved: z.boolean(),
  entries: z.array(
    z.discriminatedUnion("kind", [
      z.object({
        kind: z.literal("commentary"),
        id: z.string(),
        text: z.string(),
      }),
      z.object({
        kind: z.literal("tool"),
        id: z.string(),
        tool: z.string(),
        query: z.string(),
        status: z.enum([
          "RUNNING",
          "SUCCEEDED",
          "FAILED",
          "INTERRUPTED",
          "AWAITING_CONFIRMATION",
        ]),
        hits: z.number().int().nonnegative().nullable(),
      }),
    ]),
  ),
});

function parseProcess(value: unknown): ChatResponseProcess | undefined {
  const parsed = processSchema.safeParse(value);
  return parsed.success ? parsed.data : undefined;
}

export type ChatStreamHandlers = {
  onStatus: (payload?: {
    phase: string;
    process?: ChatResponseProcess;
  }) => void;
  onToken: (text: string, segmentId?: string) => void;
  onToolCall: (payload: ChatToolCallPayload) => void;
  onToolResult: (payload: ChatToolResultPayload) => void;
  onDone: (payload: ChatDonePayload) => void;
  onError: (payload: {
    code: string;
    detail: string;
    process?: ChatResponseProcess;
  }) => void;
};

/**
 * 发送消息并消费 SSE 回答流（POST 流 + eventsource-parser + AbortController）。
 * 非 2xx 由 apiRequest 统一抛 ApiError（如 409 在途 / 未配置供应商）。
 * webSearch=true 时本轮挂载联网搜索工具（后端无 key 时强制忽略该标志）；
 * page 为从当前路由派生的页面快照（工单 01：提示性信息，缺省不发送）；
 * authMode 为会话授权档位覆盖（工单 02：仅显式拨过才携带，缺省不发送）。
 * 停止信号经 reader.cancel() 传导并在读结束时转抛 AbortError（不把 signal 交给
 * fetch：jsdom 测试环境的 AbortSignal 与 Node fetch 存在跨 realm 类型冲突）。
 */
async function streamMessage(
  sessionId: string,
  content: string,
  handlers: ChatStreamHandlers,
  signal: AbortSignal | undefined,
  webSearch = false,
  page?: ChatPageSnapshot,
  authMode?: AuthMode,
): Promise<void> {
  if (signal?.aborted) throw abortError();
  const body: Record<string, unknown> = { content, web_search: webSearch };
  if (page) body.page = page;
  // 会话授权档位覆盖（工单 02）：仅显式拨过才携带，不携带＝全局默认档。
  if (authMode) body.auth_mode = authMode;
  const response = await apiRequest(
    `/api/chat-sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify(body),
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
          handlers.onStatus({
            phase: typeof data.phase === "string" ? data.phase : "generating",
            process: parseProcess(data.process),
          });
          break;
        case "token":
          if (typeof data.text === "string")
            handlers.onToken(
              data.text,
              typeof data.segment_id === "string" ? data.segment_id : undefined,
            );
          break;
        case "tool_call":
          if (typeof data.tool === "string" && typeof data.query === "string") {
            handlers.onToolCall({
              tool: data.tool,
              query: data.query,
              toolCallId:
                typeof data.tool_call_id === "string"
                  ? data.tool_call_id
                  : undefined,
              segmentId:
                typeof data.segment_id === "string"
                  ? data.segment_id
                  : undefined,
              process: parseProcess(data.process),
            });
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
              toolCallId:
                typeof data.tool_call_id === "string"
                  ? data.tool_call_id
                  : undefined,
              process: parseProcess(data.process),
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
              process: parseProcess(data.process),
              ...parseTurnProposalFields(data),
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
              process: parseProcess(data.process),
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
  /** 对话转知识点（对话转学习资产 V1）：把一条 AI 回答保存为目标记录的知识点。 */
  saveKnowledgePoint: (
    sessionId: string,
    messageId: string,
    body: ChatKnowledgePointSaveRequest,
  ) =>
    apiFetch<KnowledgePointOut>(
      `/api/chat-sessions/${sessionId}/messages/${messageId}/knowledge-points`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  streamMessage,
};
