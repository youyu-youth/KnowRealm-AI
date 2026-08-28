import type { components } from "@knowrealm/api-types";

export type ChatSession = components["schemas"]["ChatSessionOut"];
export type ChatMessage = components["schemas"]["ChatMessageOut"];
export type ChatSessionCreate = components["schemas"]["ChatSessionCreate"];
export type ChatRecordOption = components["schemas"]["ChatRecordOption"];

/**
 * SSE 流事件载荷（POST /chat-sessions/{id}/messages，事件名在 event: 行）。
 * 六类协议事件中的 citation / interrupt 在自由聊天阶段不产生，未列入。
 */
export type ChatStreamPayloads = {
  status: { phase: string };
  token: { text: string };
  done: { message_id: string; content: string };
  error: { code: string; detail: string };
};
