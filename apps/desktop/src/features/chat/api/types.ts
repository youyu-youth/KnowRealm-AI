import type { components } from "@knowrealm/api-types";

export type ChatSession = components["schemas"]["ChatSessionOut"];
export type ChatMessage = components["schemas"]["ChatMessageOut"];
export type ChatSessionCreate = components["schemas"]["ChatSessionCreate"];
export type ChatRecordOption = components["schemas"]["ChatRecordOption"];
export type ChatCitation = components["schemas"]["ChatCitationOut"];

/** web 来源条目（URL+标题，无逐字摘录）；历史行无 source 键视为 record。 */
export type WebCitation = ChatCitation & {
  source: "web";
  url: string;
  title: string;
};

export type RecordCitation = ChatCitation & {
  source: "record";
  record_id: string;
  quote: string;
};

export function isWebCitation(citation: ChatCitation): citation is WebCitation {
  return citation.source === "web";
}

export function isRecordCitation(
  citation: ChatCitation,
): citation is RecordCitation {
  return citation.source !== "web";
}

/**
 * SSE 流事件载荷（POST /chat-sessions/{id}/messages，事件名在 event: 行）。
 * citation 随流下发但渲染以 REST 的 citations 字段为事实源（done 后重取），
 * 故前端不单独消费；形状与 ChatCitationOut 同构（record/web 判别）。
 * interrupt 在当前阶段不产生，未列入。
 */
export type ChatStreamPayloads = {
  status: { phase: string };
  token: { text: string };
  citation:
    | { index: number; source: "record"; record_id: string; quote: string }
    | { index: number; source: "web"; url: string; title: string };
  done: { message_id: string; content: string };
  error: { code: string; detail: string };
};
