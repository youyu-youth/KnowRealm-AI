// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { ChatResearchProposalCard } from "./ChatResearchProposalCard";

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
  researchProposals: { proposalId: string; url: string; title: string }[],
  sessionId = SESSION_ID,
) {
  useChatUiStore.setState({
    turnMemory: {
      sessionId,
      memoryUsed: [],
      proposals: [],
      researchProposals,
      operationProposals: [],
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useChatUiStore.setState({ turnMemory: null });
});

describe("ChatResearchProposalCard", () => {
  it("当轮无入库提案时不渲染", () => {
    setTurnMemory([]);
    const { container } = renderWithQuery(
      <ChatResearchProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("其他会话的当轮提案不渲染", () => {
    setTurnMemory(
      [{ proposalId: "p-9", url: "https://a.example.com", title: "来源 A" }],
      "session-2",
    );
    const { container } = renderWithQuery(
      <ChatResearchProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("逐条展示标题与域名，确认调用 confirm 并显示已入库", async () => {
    confirmProposal.mockResolvedValue({ status: "APPLIED" });
    setTurnMemory([
      {
        proposalId: "p-1",
        url: "https://a.example.com/post/1",
        title: "来源 A",
      },
      { proposalId: "p-2", url: "https://b.example.com/x", title: "来源 B" },
    ]);
    renderWithQuery(<ChatResearchProposalCard sessionId={SESSION_ID} />);
    expect(screen.getByText("来源 A")).toBeVisible();
    expect(screen.getByText("a.example.com")).toBeVisible();
    expect(screen.getByText("来源 B")).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: "保存「来源 A」到资料库" }),
    );
    await waitFor(() => {
      expect(confirmProposal).toHaveBeenCalledWith("p-1");
    });
    expect(await screen.findByText("已确认入库，等待抓取完成。")).toBeVisible();
    // 已处理条目从待确认列表消失，另一条仍在。
    expect(
      screen.queryByText("保存「来源 A」到资料库"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "保存「来源 B」到资料库" }),
    ).toBeEnabled();
  });

  it("拒绝调用 reject 且零事实变更", async () => {
    rejectProposal.mockResolvedValue({ status: "REJECTED" });
    setTurnMemory([
      { proposalId: "p-2", url: "https://b.example.com/x", title: "来源 B" },
    ]);
    renderWithQuery(<ChatResearchProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(screen.getByRole("button", { name: "拒绝保存「来源 B」" }));
    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("p-2");
    });
    expect(await screen.findByText("已拒绝该来源，未入库。")).toBeVisible();
    expect(confirmProposal).not.toHaveBeenCalled();
  });
});
