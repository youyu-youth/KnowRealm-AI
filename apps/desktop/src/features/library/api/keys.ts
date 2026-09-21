export const libraryKeys = {
  all: ["library"] as const,
  items: (params: Record<string, unknown> = {}) =>
    [...libraryKeys.all, "items", params] as const,
  itemDetail: (itemId: string) =>
    [...libraryKeys.all, "itemDetail", itemId] as const,
  itemContent: (itemId: string) =>
    [...libraryKeys.all, "itemContent", itemId] as const,
  records: () => [...libraryKeys.all, "records"] as const,
  assets: () => [...libraryKeys.all, "assets"] as const,
  organizeScan: () => [...libraryKeys.all, "organizeScan"] as const,
  proposals: (status: string) =>
    [...libraryKeys.all, "proposals", status] as const,
  /** 本会话全状态提案（操作提案卡恢复源，工单 02 review）；后端 session_id 过滤。 */
  sessionProposals: (sessionId: string) =>
    [...libraryKeys.all, "proposals", "session", sessionId] as const,
};
