import type { components } from "@knowrealm/api-types";

export type ChatSession = components["schemas"]["ChatSessionOut"];
export type ChatMessage = components["schemas"]["ChatMessageOut"];
export type ChatSessionCreate = components["schemas"]["ChatSessionCreate"];
export type ChatRecordOption = components["schemas"]["ChatRecordOption"];
export type ChatCitation = components["schemas"]["ChatCitationOut"];
/** 随消息携带的页面快照（通用 Agent 工单 01）：提示性信息，不构成授权。 */
export type ChatPageSnapshot = components["schemas"]["ChatPageSnapshot"];
/** 对话转知识点（对话转学习资产 V1）请求体与保存产物。 */
export type ChatKnowledgePointSaveRequest =
  components["schemas"]["ChatKnowledgePointSaveRequest"];
export type KnowledgePointOut = components["schemas"]["KnowledgePointOut"];

/** web 来源条目（URL+标题，无逐字摘录）；历史行无 source 键视为 record。 */
export type WebCitation = ChatCitation & {
  source: "web";
  url: string;
  title: string;
};

/** library 来源条目（资料条目正文摘录，工单 04）：跳转资料库来源预览。 */
export type LibraryCitation = ChatCitation & {
  source: "library";
  library_item_id: string;
  quote: string;
  title?: string | null;
};

export type RecordCitation = ChatCitation & {
  source: "record";
  record_id: string;
  quote: string;
};

export function isWebCitation(citation: ChatCitation): citation is WebCitation {
  return citation.source === "web";
}

export function isLibraryCitation(
  citation: ChatCitation,
): citation is LibraryCitation {
  return citation.source === "library";
}

export function isRecordCitation(
  citation: ChatCitation,
): citation is RecordCitation {
  return citation.source !== "web" && citation.source !== "library";
}

/**
 * SSE 流事件载荷（POST /chat-sessions/{id}/messages，事件名在 event: 行）。
 * citation 随流下发但渲染以 REST 的 citations 字段为事实源（done 后重取），
 * 故前端不单独消费；形状与 ChatCitationOut 同构（record/web/library 判别）。
 * interrupt 在当前阶段不产生，未列入。
 */
export type ChatStreamPayloads = {
  status: { phase: string };
  token: { text: string };
  citation:
    | { index: number; source: "record"; record_id: string; quote: string }
    | { index: number; source: "web"; url: string; title: string }
    | {
        index: number;
        source: "library";
        library_item_id: string;
        quote: string;
        title?: string | null;
      };
  done: { message_id: string; content: string };
  error: { code: string; detail: string };
};
