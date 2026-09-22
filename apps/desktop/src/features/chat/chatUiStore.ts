import { create } from "zustand";
import type { AuthMode } from "@/features/agent/api/authMode";
import type {
  ChatExecutedOperationPayload,
  ChatMemoryProposalPayload,
  ChatResearchProposalPayload,
} from "@/features/chat/api/chatSessions";

/** 本轮学习者记忆与入库提案的临时展示态（工单 06 / 研究会话 V1）：done 载荷的
 * 唯一消费来源，不落库（提案本体已在 agent_proposals 表跨重启持久）。
 * 同一时间只保留一条活跃会话的记忆态；切换会话或再次发送即清除。 */
export type ChatTurnMemory = {
  sessionId: string;
  /** 本轮实际注入的记忆条目（空数组 = 确认未注入）。 */
  memoryUsed: string[];
  /** 模型本轮新建的待确认 MEMORY 提案。 */
  proposals: ChatMemoryProposalPayload[];
  /** 模型本轮经 propose_ingest 新建的待确认入库提案（研究会话）。 */
  researchProposals: ChatResearchProposalPayload[];
};

/** 本轮直执行回执的临时展示态（通用 Agent 第二阶段工单 02）：done 载荷的消费
 * 来源，事实源是 agent_operations 表（回执卡经会话过滤查询恢复）；本态仅用于
 * 「查询缺席＝历史已清理」占位判定与同轮即时呈现，再次发送即清除。 */
export type ChatTurnExecuted = {
  sessionId: string;
  operations: ChatExecutedOperationPayload[];
};

export const CHAT_TOOL_IDS = [
  "webSearch",
  "knowledgeBase",
  "codeRun",
  "documentParse",
] as const;

export type ChatToolId = (typeof CHAT_TOOL_IDS)[number];

/** 示意开关（图 1 对齐的本地假状态）；webSearch 已接真，走 webSearchBySession。 */
export const CHAT_DEMO_TOOL_IDS = [
  "knowledgeBase",
  "codeRun",
  "documentParse",
] as const;

export type ChatDemoToolId = (typeof CHAT_DEMO_TOOL_IDS)[number];

type ChatUiState = {
  /**
   * 会话收藏与示意工具开关是图 1 对齐的本地状态：
   * 只在本进程内生效，不落库。
   */
  favoriteSessionIds: ReadonlySet<string>;
  tools: Record<ChatDemoToolId, boolean>;
  /** 联网搜索开关按会话记忆（重启重置）；缺省值经 selectWebSearchEnabled 取「自由 ON / 挂载 OFF」。 */
  webSearchBySession: Record<string, boolean>;
  /** 会话授权档位按会话记忆（通用 Agent 工单 02）：显式拨过才覆盖全局默认，
   * 重启应用回落全局默认（安全方向）；发送消息时携带覆盖，不携带＝全局默认。 */
  authModeBySession: Record<string, AuthMode>;
  /** 本轮学习者记忆（消息流确认卡与右栏注入展示共用，done 时写入）。 */
  turnMemory: ChatTurnMemory | null;
  setTurnMemory: (memory: ChatTurnMemory) => void;
  clearTurnMemory: (sessionId: string) => void;
  /** 本轮直执行回执（占位判定用，done 时写入）。 */
  turnExecuted: ChatTurnExecuted | null;
  setTurnExecuted: (executed: ChatTurnExecuted) => void;
  clearTurnExecuted: (sessionId: string) => void;
  toggleFavorite: (sessionId: string) => void;
  toggleTool: (tool: ChatDemoToolId) => void;
  setWebSearchEnabled: (sessionId: string, enabled: boolean) => void;
  setSessionAuthMode: (sessionId: string, mode: AuthMode) => void;
};

export const useChatUiStore = create<ChatUiState>((set) => ({
  favoriteSessionIds: new Set<string>(),
  tools: {
    knowledgeBase: true,
    codeRun: true,
    documentParse: true,
  },
  webSearchBySession: {},
  authModeBySession: {},
  turnMemory: null,
  turnExecuted: null,
  setTurnMemory: (memory) => set({ turnMemory: memory }),
  clearTurnMemory: (sessionId) =>
    set((state) =>
      state.turnMemory?.sessionId === sessionId ? { turnMemory: null } : state,
    ),
  setTurnExecuted: (executed) => set({ turnExecuted: executed }),
  clearTurnExecuted: (sessionId) =>
    set((state) =>
      state.turnExecuted?.sessionId === sessionId
        ? { turnExecuted: null }
        : state,
    ),
  toggleFavorite: (sessionId) =>
    set((state) => {
      const next = new Set(state.favoriteSessionIds);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return { favoriteSessionIds: next };
    }),
  toggleTool: (tool) =>
    set((state) => ({ tools: { ...state.tools, [tool]: !state.tools[tool] } })),
  setWebSearchEnabled: (sessionId, enabled) =>
    set((state) => ({
      webSearchBySession: { ...state.webSearchBySession, [sessionId]: enabled },
    })),
  setSessionAuthMode: (sessionId, mode) =>
    set((state) => ({
      authModeBySession: { ...state.authModeBySession, [sessionId]: mode },
    })),
}));

/** 联网开关当前值：用户拨过按会话记忆，否则按会话类型取默认
 * （研究会话恒 ON；普通会话自由 ON / 挂载 OFF）。 */
export function selectWebSearchEnabled(
  state: Pick<ChatUiState, "webSearchBySession">,
  sessionId: string,
  mounted: boolean,
  research = false,
): boolean {
  return state.webSearchBySession[sessionId] ?? (research || !mounted);
}
