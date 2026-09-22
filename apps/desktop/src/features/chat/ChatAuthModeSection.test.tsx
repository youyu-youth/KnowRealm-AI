// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatAuthModeSection } from "./ChatAuthModeSection";
import { useChatUiStore } from "./chatUiStore";

const { getAuthMode, postSessionSwitch } = vi.hoisted(() => ({
  getAuthMode: vi.fn(),
  postSessionSwitch: vi.fn(),
}));

vi.mock("@/features/agent/api/authMode", () => ({
  AUTH_MODES: ["REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"],
  agentAuthApi: { getAuthMode, postSessionSwitch },
  agentKeys: {
    authMode: ["agent", "auth-mode"],
    sessionOperations: (sessionId: string) => [
      "agent",
      "operations",
      sessionId,
    ],
  },
  isAuthMode: (value: unknown) =>
    typeof value === "string" &&
    ["REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"].includes(value),
}));

const SESSION_ID = "session-1";

beforeEach(() => {
  vi.clearAllMocks();
  getAuthMode.mockResolvedValue({ auth_mode: "REQUEST_APPROVAL" });
  postSessionSwitch.mockResolvedValue({ auth_mode: "AUTO_APPROVE" });
  useChatUiStore.setState({ authModeBySession: {} });
});

describe("ChatAuthModeSection", () => {
  it("未拨过时显示全局默认档", async () => {
    renderWithQuery(<ChatAuthModeSection sessionId={SESSION_ID} />);

    const trigger = await screen.findByRole("combobox");
    await waitFor(() => expect(trigger).toBeEnabled());
    expect(trigger).toHaveTextContent("请求批准");
  });

  it("切换先写会话审计，成功后本地覆盖生效", async () => {
    renderWithQuery(<ChatAuthModeSection sessionId={SESSION_ID} />);

    const trigger = await screen.findByRole("combobox");
    await waitFor(() => expect(trigger).toBeEnabled());
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: "帮我批准" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);

    await waitFor(() =>
      expect(postSessionSwitch).toHaveBeenCalledWith(
        SESSION_ID,
        "REQUEST_APPROVAL",
        "AUTO_APPROVE",
      ),
    );
    // 本地覆盖生效：触发器呈现新档（会话档位为前端内存态）。
    await waitFor(() => expect(trigger).toHaveTextContent("帮我批准"));
    expect(useChatUiStore.getState().authModeBySession[SESSION_ID]).toBe(
      "AUTO_APPROVE",
    );
  });

  it("审计失败呈现错误且档位不变", async () => {
    postSessionSwitch.mockRejectedValue(new Error("审计写入失败"));
    renderWithQuery(<ChatAuthModeSection sessionId={SESSION_ID} />);

    const trigger = await screen.findByRole("combobox");
    await waitFor(() => expect(trigger).toBeEnabled());
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: "完全访问" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);

    expect(await screen.findByRole("alert")).toHaveTextContent("审计写入失败");
    expect(trigger).toHaveTextContent("请求批准");
    expect(
      useChatUiStore.getState().authModeBySession[SESSION_ID],
    ).toBeUndefined();
  });
});
