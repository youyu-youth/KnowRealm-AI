// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { useChatUiStore } from "@/features/chat/chatUiStore";
import { ChatOperationProposalCard } from "./ChatOperationProposalCard";

const { confirmProposal, rejectProposal, listProposals } = vi.hoisted(() => ({
  confirmProposal: vi.fn(),
  rejectProposal: vi.fn(),
  listProposals: vi.fn(),
}));

vi.mock("@/features/library/api/library", () => ({
  libraryApi: {
    confirmProposal,
    rejectProposal,
    listProposals,
  },
}));

// 组件级测试没有 RouterProvider：仅把 Link 降级为普通锚点，其余 router 导出保持原样。
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    Link: ({
      to,
      children,
    }: {
      to?: unknown;
      children?: ReactNode;
      params?: unknown;
    }) => <a href={typeof to === "string" ? to : "#"}>{children}</a>,
  };
});

const SESSION_ID = "session-1";

const SCHOOL_PAYLOAD = {
  name: "高中物理",
  learning_context: "SCHOOL",
  education_stage: "HIGH_SCHOOL",
  depth: null,
  course_type: null,
  description: null,
};

function setTurnMemory(
  operationProposals: {
    proposalId: string;
    action: string;
    payload: Record<string, unknown>;
  }[],
  sessionId = SESSION_ID,
) {
  useChatUiStore.setState({
    turnMemory: {
      sessionId,
      memoryUsed: [],
      proposals: [],
      researchProposals: [],
      operationProposals,
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useChatUiStore.setState({ turnMemory: null });
  listProposals.mockResolvedValue([]);
});

describe("ChatOperationProposalCard", () => {
  it("当轮与恢复查询均无提案时不渲染", () => {
    const { container } = renderWithQuery(
      <ChatOperationProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("完整参数预览：读提案 payload 并把枚举值翻译为中文", () => {
    setTurnMemory([
      {
        proposalId: "p-1",
        action: "create_course",
        payload: SCHOOL_PAYLOAD,
      },
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(screen.getByText("课程创建提案")).toBeVisible();
    expect(screen.getByText("高中物理")).toBeVisible();
    expect(screen.getByText("学业学习")).toBeVisible();
    expect(screen.getByText("高中")).toBeVisible();
    // 可选字段缺省时不渲染空行。
    expect(screen.queryByText("课程类型（可选）")).not.toBeInTheDocument();
  });

  it("确认调用 confirm 并转回执态、提供课程入口", async () => {
    confirmProposal.mockResolvedValue({
      status: "APPLIED",
      result: { course_id: "course-9" },
    });
    setTurnMemory([
      {
        proposalId: "p-1",
        action: "create_course",
        payload: SCHOOL_PAYLOAD,
      },
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(screen.getByRole("button", { name: "确认创建课程" }));
    await waitFor(() => {
      expect(confirmProposal).toHaveBeenCalledWith("p-1");
    });
    expect(await screen.findByText("课程已创建。")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开课程" });
    expect(link).toHaveAttribute("href", "/spaces/$courseId");
  });

  it("拒绝调用 reject 且不创建课程", async () => {
    rejectProposal.mockResolvedValue({ status: "REJECTED" });
    setTurnMemory([
      {
        proposalId: "p-2",
        action: "create_course",
        payload: SCHOOL_PAYLOAD,
      },
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(screen.getByRole("button", { name: "拒绝创建课程" }));
    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("p-2");
    });
    expect(await screen.findByText("已拒绝，未创建课程。")).toBeVisible();
    expect(confirmProposal).not.toHaveBeenCalled();
  });

  it("断线/重启后经既有提案查询恢复本会话待确认提案", async () => {
    listProposals.mockResolvedValue([
      {
        id: "p-r1",
        proposal_type: "COURSE_CREATE",
        status: "PENDING",
        session_id: SESSION_ID,
        payload: SCHOOL_PAYLOAD,
        result: null,
      },
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(
      await screen.findByRole("button", { name: "确认创建课程" }),
    ).toBeEnabled();
    expect(listProposals).toHaveBeenCalledWith({ status: "PENDING" });
  });

  it("其他会话的恢复提案不渲染", async () => {
    listProposals.mockResolvedValue([
      {
        id: "p-r2",
        proposal_type: "COURSE_CREATE",
        status: "PENDING",
        session_id: "session-2",
        payload: SCHOOL_PAYLOAD,
        result: null,
      },
    ]);
    const { container } = renderWithQuery(
      <ChatOperationProposalCard sessionId={SESSION_ID} />,
    );
    await screen.findByText("课程创建提案").catch(() => undefined);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});
