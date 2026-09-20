// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatMemoryPanel } from "./ChatMemoryPanel";

const { confirmProposal, rejectProposal } = vi.hoisted(() => ({
  confirmProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));

vi.mock("@/features/library/api/library", () => ({
  libraryApi: {
    confirmProposal,
    rejectProposal,
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ChatMemoryPanel", () => {
  it("本轮无注入且无提案时不渲染", () => {
    const { container } = renderWithQuery(
      <ChatMemoryPanel used={null} proposals={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("展示本轮注入的记忆条目", () => {
    renderWithQuery(
      <ChatMemoryPanel used={["先看例题", "多给反例"]} proposals={[]} />,
    );
    expect(
      screen.getByRole("region", { name: "本轮 AI 记忆" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("已注入的记忆：先看例题、多给反例"),
    ).toBeInTheDocument();
  });

  it("本轮零注入（外发关闭/无记忆）展示空态说明", () => {
    renderWithQuery(<ChatMemoryPanel used={[]} proposals={[]} />);
    expect(
      screen.getByRole("region", { name: "本轮 AI 记忆" }),
    ).toBeInTheDocument();
    expect(screen.getByText("本轮未使用任何记忆。")).toBeInTheDocument();
  });

  it("确认记忆提案调用 confirm 并显示已记住", async () => {
    confirmProposal.mockResolvedValue({ status: "APPLIED" });
    renderWithQuery(
      <ChatMemoryPanel
        used={null}
        proposals={[{ proposalId: "p-1", items: ["先看例题"] }]}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "接受记忆「先看例题」" }),
    );
    await waitFor(() => {
      expect(confirmProposal).toHaveBeenCalledWith("p-1");
    });
    expect(await screen.findByText("已记住，感谢确认。")).toBeInTheDocument();
  });

  it("拒绝记忆提案调用 reject 且不改任何事实", async () => {
    rejectProposal.mockResolvedValue({ status: "REJECTED" });
    renderWithQuery(
      <ChatMemoryPanel
        used={[]}
        proposals={[{ proposalId: "p-2", items: ["先看例题"] }]}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "拒绝记忆「先看例题」" }),
    );
    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("p-2");
    });
    expect(
      await screen.findByText("已拒绝该记忆提案，未做任何记录。"),
    ).toBeInTheDocument();
    expect(confirmProposal).not.toHaveBeenCalled();
  });
});
