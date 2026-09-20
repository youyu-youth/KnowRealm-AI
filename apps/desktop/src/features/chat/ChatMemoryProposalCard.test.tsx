// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { ChatMemoryProposalCard } from "./ChatMemoryProposalCard";

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

const SESSION_ID = "session-1";

function setTurnMemory(
  proposals: { proposalId: string; items: string[] }[] = [],
) {
  useChatUiStore.setState({
    turnMemory: { sessionId: SESSION_ID, memoryUsed: [], proposals },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useChatUiStore.setState({ turnMemory: null });
});

describe("ChatMemoryProposalCard", () => {
  it("当轮无提案时不渲染", () => {
    setTurnMemory([]);
    const { container } = renderWithQuery(
      <ChatMemoryProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("其他会话的当轮记忆不渲染", () => {
    useChatUiStore.setState({
      turnMemory: {
        sessionId: "session-2",
        memoryUsed: [],
        proposals: [{ proposalId: "p-9", items: ["a"] }],
      },
    });
    const { container } = renderWithQuery(
      <ChatMemoryProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("确认记忆提案调用 confirm 并显示已记住", async () => {
    confirmProposal.mockResolvedValue({ status: "APPLIED" });
    setTurnMemory([{ proposalId: "p-1", items: ["先看例题"] }]);
    renderWithQuery(<ChatMemoryProposalCard sessionId={SESSION_ID} />);
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
    setTurnMemory([{ proposalId: "p-2", items: ["先看例题"] }]);
    renderWithQuery(<ChatMemoryProposalCard sessionId={SESSION_ID} />);
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
