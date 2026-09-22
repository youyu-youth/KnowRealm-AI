// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { AgentAutomationSection } from "./AgentAutomationSection";

const { getAuthMode, putAuthMode } = vi.hoisted(() => ({
  getAuthMode: vi.fn(),
  putAuthMode: vi.fn(),
}));

vi.mock("@/features/agent/api/authMode", () => ({
  AUTH_MODES: ["REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"],
  agentAuthApi: { getAuthMode, putAuthMode },
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

beforeEach(() => {
  vi.clearAllMocks();
  getAuthMode.mockResolvedValue({ auth_mode: "REQUEST_APPROVAL" });
});

describe("AgentAutomationSection", () => {
  it("呈现当前全局默认档与三档说明", async () => {
    renderWithQuery(<AgentAutomationSection />);

    expect(
      await screen.findByRole("radio", { name: "请求批准" }),
    ).toBeVisible();
    expect(screen.getByRole("radio", { name: "帮我批准" })).toBeVisible();
    expect(screen.getByRole("radio", { name: "完全访问" })).toBeVisible();
    expect(
      screen.getByText(/每个写操作先出确认卡，确认后才执行。/),
    ).toBeVisible();
  });

  it("切换全局默认档调用 PUT（from 由后端自读，只声明目标档）", async () => {
    putAuthMode.mockResolvedValue({ auth_mode: "FULL_ACCESS" });
    renderWithQuery(<AgentAutomationSection />);

    await screen.findByRole("radio", { name: "完全访问" });
    fireEvent.click(screen.getByRole("radio", { name: "完全访问" }));

    await waitFor(() =>
      expect(putAuthMode).toHaveBeenCalledWith("FULL_ACCESS"),
    );
  });

  it("切换失败呈现错误且档位不变", async () => {
    putAuthMode.mockRejectedValue(new Error("网络异常"));
    renderWithQuery(<AgentAutomationSection />);

    await screen.findByRole("radio", { name: "帮我批准" });
    fireEvent.click(screen.getByRole("radio", { name: "帮我批准" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("网络异常");
  });
});
