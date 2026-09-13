import { create } from "zustand";

export const CHAT_TOOL_IDS = [
  "webSearch",
  "knowledgeBase",
  "codeRun",
  "documentParse",
] as const;

export type ChatToolId = (typeof CHAT_TOOL_IDS)[number];

type ChatUiState = {
  /**
   * 会话收藏与工具开关是图 1 对齐的本地示意状态（假数据）：
   * 只在本进程内生效，不落库、不参与任何后端请求。
   */
  favoriteSessionIds: ReadonlySet<string>;
  tools: Record<ChatToolId, boolean>;
  toggleFavorite: (sessionId: string) => void;
  toggleTool: (tool: ChatToolId) => void;
};

export const useChatUiStore = create<ChatUiState>((set) => ({
  favoriteSessionIds: new Set<string>(),
  tools: {
    webSearch: true,
    knowledgeBase: true,
    codeRun: true,
    documentParse: true,
  },
  toggleFavorite: (sessionId) =>
    set((state) => {
      const next = new Set(state.favoriteSessionIds);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return { favoriteSessionIds: next };
    }),
  toggleTool: (tool) =>
    set((state) => ({ tools: { ...state.tools, [tool]: !state.tools[tool] } })),
}));
