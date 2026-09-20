import { describe, expect, it } from "vitest";
import { selectWebSearchEnabled } from "@/features/chat/chatUiStore";

function stateWith(webSearchBySession: Record<string, boolean>) {
  return { webSearchBySession };
}

describe("selectWebSearchEnabled", () => {
  it("研究会话默认开启（不区分是否挂载范围）", () => {
    expect(selectWebSearchEnabled(stateWith({}), "s1", false, true)).toBe(true);
    expect(selectWebSearchEnabled(stateWith({}), "s1", true, true)).toBe(true);
  });

  it("普通会话维持自由 ON / 挂载 OFF 的默认", () => {
    expect(selectWebSearchEnabled(stateWith({}), "s1", false, false)).toBe(
      true,
    );
    expect(selectWebSearchEnabled(stateWith({}), "s1", true, false)).toBe(
      false,
    );
  });

  it("用户拨过的会话按会话记忆，研究默认不覆盖显式值", () => {
    expect(
      selectWebSearchEnabled(stateWith({ s1: false }), "s1", false, true),
    ).toBe(false);
    expect(
      selectWebSearchEnabled(stateWith({ s2: true }), "s2", true, false),
    ).toBe(true);
  });
});
