/**
 * 页面快照（通用 Agent 工单 01）：发送消息时从当前路由派生的轻量上下文。
 *
 * 仅提示用户当前所在页面，不落库、不构成授权、不扩大读取范围；后端注入前
 * 会重新校验对象存在性与状态。当前唯一发送入口是 /chat 会话页，恒派生
 * chat；对话发送面扩展到其他页面时（如课程页内嵌对话）再引入路由参数按
 * 页面补充派生分支，后端契约（ChatPageSnapshot 的 page_type 枚举）已预留。
 */
import type { ChatPageSnapshot } from "@/features/chat/api/types";

export function derivePageSnapshot(): ChatPageSnapshot {
  return { page_type: "chat", captured_at: new Date().toISOString() };
}
