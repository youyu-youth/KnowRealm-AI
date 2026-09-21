import { describe, expect, it } from "vitest";
import { derivePageSnapshot } from "@/features/chat/pageSnapshot";

describe("derivePageSnapshot", () => {
  it("当前唯一发送入口是 /chat 会话页：恒派生 chat", () => {
    expect(derivePageSnapshot()).toEqual({
      page_type: "chat",
      captured_at: expect.any(String),
    });
  });
});
