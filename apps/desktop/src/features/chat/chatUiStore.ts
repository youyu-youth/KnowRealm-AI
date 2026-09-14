import { create } from "zustand";

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
  toggleFavorite: (sessionId: string) => void;
  toggleTool: (tool: ChatDemoToolId) => void;
  setWebSearchEnabled: (sessionId: string, enabled: boolean) => void;
};

export const useChatUiStore = create<ChatUiState>((set) => ({
  favoriteSessionIds: new Set<string>(),
  tools: {
    knowledgeBase: true,
    codeRun: true,
    documentParse: true,
  },
  webSearchBySession: {},
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
}));

/** 联网开关当前值：用户拨过按会话记忆，否则按会话类型取默认（自由 ON / 挂载 OFF）。 */
export function selectWebSearchEnabled(
  state: Pick<ChatUiState, "webSearchBySession">,
  sessionId: string,
  mounted: boolean,
): boolean {
  return state.webSearchBySession[sessionId] ?? !mounted;
}
