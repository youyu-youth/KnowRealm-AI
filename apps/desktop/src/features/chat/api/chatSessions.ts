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
  ChatTurn,
  ChatTurnResult,
  ChatTurnsPage,
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

/** 历史行轮次载荷的展示子集解析（与 done 载荷同一防御性收窄，规格 §15 恢复入口）。 */
export function parseTurnResult(result: ChatTurnResult | null | undefined): {
  memoryUsed: string[];
  proposals: ChatMemoryProposalPayload[];
  researchProposals: ChatResearchProposalPayload[];
} | null {
  if (result == null) return null;
  const parsed = parseTurnProposalFields({ ...result });
  return {
    memoryUsed: parsed.memoryUsed ?? [],
    proposals: parsed.memoryProposals ?? [],
    researchProposals: parsed.researchProposals ?? [],
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

function abortError(): Error {
  const error = new Error("Aborted");
  error.name = "AbortError";
  return error;
}

export type TurnStreamHandlers = {
  onStatus: (payload: { phase: string; process?: ChatResponseProcess }) => void;
  onToken: (text: string, segmentId?: string) => void;
  onToolCall: (payload: ChatToolCallPayload) => void;
  onToolResult: (payload: ChatToolResultPayload) => void;
  onDone: (payload: ChatDonePayload) => void;
  onError: (payload: { code: string; detail: string }) => void;
};

/**
 * 订阅轮次已提交事件（GET 流 + eventsource-parser + AbortController）。
 * 连接只承载观察：断开 / 卸载 / 切换会话经 signal 关闭订阅，业务停止必须走
 * cancel 端点的持久指令（切换会话不中断任务，票 01）。
 */
async function turnEvents(
  turnId: string,
  afterSeq: number,
  handlers: TurnStreamHandlers,
  signal: AbortSignal | undefined,
): Promise<void> {
  if (signal?.aborted) throw abortError();
  const response = await apiRequest(
    `/api/chat-turns/${turnId}/events?after_seq=${afterSeq}`,
    { headers: { Accept: "text/event-stream" } },
  );
  if (!response.body) throw new Error("turn events response has no body");
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
        case "citation":
          // 引用渲染以最终消息的 citations 为事实源（done 后重取），不单独消费。
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
  /** 提交回答生成轮次（票 01）：202 原子受理，request_id 网络重试中保持稳定。 */
  submitTurn: (
    sessionId: string,
    body: {
      content: string;
      webSearch: boolean;
      requestId: string;
      page?: ChatPageSnapshot;
      authMode?: AuthMode;
    },
  ) => {
    const payload: Record<string, unknown> = {
      content: body.content,
      web_search: body.webSearch,
      request_id: body.requestId,
    };
    if (body.page) payload.page = body.page;
    if (body.authMode) payload.auth_mode = body.authMode;
    return apiFetch<ChatTurn>(`/api/chat-sessions/${sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  /** 会话当前非终态轮次（至多一条；无在途时 null）。 */
  activeTurn: async (sessionId: string): Promise<ChatTurn | null> => {
    const page = await apiFetch<ChatTurnsPage>(
      `/api/chat-sessions/${sessionId}/turns?active_only=true&limit=1`,
    );
    return page.turns[0] ?? null;
  },
  getTurn: (turnId: string) => apiFetch<ChatTurn>(`/api/chat-turns/${turnId}`),
  /** 持久停止指令（票 01）：返回实际状态与 cancel_requested（RUNNING＝正在停止）。 */
  cancelTurn: (turnId: string) =>
    apiFetch<{ turn: ChatTurn }>(`/api/chat-turns/${turnId}/cancel`, {
      method: "POST",
    }),
  turnEvents,
};
