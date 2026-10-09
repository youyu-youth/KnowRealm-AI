// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import type { ChatMessage } from "@/features/chat/api/types";
import { deriveTurnMemory } from "@/features/chat/turnMemory";

const SESSION_ID = "session-1";

function userMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "user-1",
    session_id: SESSION_ID,
    role: "USER",
    content: "问题",
    citations: [],
    model: null,
    token_usage: null,
    created_at: "2026-10-09T10:00:00.000000Z",
    response_processes: [],
    ...overrides,
  } as ChatMessage;
}

describe("deriveTurnMemory — 历史轮次载荷恢复（规格 §5/§15）", () => {
  it("取最近一条带完成载荷的轮次并解析记忆与提案", () => {
    const memory = deriveTurnMemory(
      [
        userMessage({ id: "user-1" }),
        userMessage({
          id: "user-2",
          turn: {
            id: "turn-2",
            status: "COMPLETED",
            output_text: "",
            result: {
              memory_used: ["偏好中文"],
              memory_proposals: [{ proposal_id: "p-1", items: ["喜欢算法"] }],
              research_proposals: [
                {
                  proposal_id: "p-2",
                  url: "https://example.com/a",
                  title: "文章",
                },
              ],
            },
          },
        }),
      ],
      SESSION_ID,
    );
    expect(memory).toEqual({
      sessionId: SESSION_ID,
      memoryUsed: ["偏好中文"],
      proposals: [{ proposalId: "p-1", items: ["喜欢算法"] }],
      researchProposals: [
        { proposalId: "p-2", url: "https://example.com/a", title: "文章" },
      ],
    });
  });

  it("最新轮次无完成载荷时回退到更早的完成轮次", () => {
    const memory = deriveTurnMemory(
      [
        userMessage({
          id: "user-1",
          turn: {
            id: "turn-1",
            status: "COMPLETED",
            output_text: "",
            result: { memory_used: ["旧记忆"] },
          },
        }),
        userMessage({
          id: "user-2",
          turn: {
            id: "turn-2",
            status: "CANCELLED",
            output_text: "半截",
            result: null,
          },
        }),
      ],
      SESSION_ID,
    );
    expect(memory?.memoryUsed).toEqual(["旧记忆"]);
  });

  it("无任何完成载荷（取消 / 失败轮次）返回 null", () => {
    const memory = deriveTurnMemory(
      [
        userMessage({
          turn: {
            id: "turn-1",
            status: "FAILED",
            output_text: "半截",
            result: null,
          },
        }),
      ],
      SESSION_ID,
    );
    expect(memory).toBeNull();
  });
});
