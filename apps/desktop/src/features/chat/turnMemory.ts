import type { ChatMessage } from "@/features/chat/api/types";
import { parseTurnResult } from "@/features/chat/api/chatSessions";
import type { ChatTurnMemory } from "@/features/chat/chatUiStore";

/** 历史消息的轮次载荷 → 当轮展示态（规格 §5/§15 成果恢复入口）。
 *
 * 离开期间完成的轮次不会经过本客户端的 done 事件；确认卡与记忆注入展示据此从
 * 历史行恢复。取最近一条带完成载荷的轮次（补答复用同一 user 消息时，后端按最新
 * 轮次合并，与「同一时间只保留一条活跃记忆态」的当轮语义一致）。 */
export function deriveTurnMemory(
  messages: ChatMessage[],
  sessionId: string,
): ChatTurnMemory | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const parsed = parseTurnResult(messages[index].turn?.result);
    if (parsed === null) continue;
    return {
      sessionId,
      memoryUsed: parsed.memoryUsed,
      proposals: parsed.proposals,
      researchProposals: parsed.researchProposals,
    };
  }
  return null;
}
