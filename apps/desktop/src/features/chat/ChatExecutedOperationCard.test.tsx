// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatExecutedOperationCard } from "./ChatExecutedOperationCard";
import { useChatUiStore } from "./chatUiStore";

const { listOperations } = vi.hoisted(() => ({
  listOperations: vi.fn(),
}));

vi.mock("@/features/settings/api/operationHistory", () => ({
  operationHistoryApi: { listOperations },
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

function operationFixture(
  overrides: Partial<{
    id: string;
    action: string;
    status: string;
    proposal_id: string | null;
    result: Record<string, string> | null;
    error_code: string | null;
    authorization: Record<string, unknown> | null;
    finished_at: string | null;
  }> = {},
) {
  return {
    id: "op-1",
    run_id: null,
    proposal_id: null,
    action: "create_course",
    level: "L1",
    target_type: null,
    target_id: null,
    payload: { name: "自动化物理" },
    snapshot: null,
    authorization: {
      auth_mode: "AUTO_APPROVE",
      trigger: "AUTO_EXECUTED",
      instruction_excerpt: "帮我建一门物理课",
      session_id: SESSION_ID,
      message_id: "m-1",
    },
    status: "SUCCEEDED",
    attempts: 1,
    result: { course_id: "course-9" },
    error_code: null,
    undo_of: null,
    undone_by: null,
    created_at: "2026-09-23T08:00:00.000000Z",
    updated_at: "2026-09-23T08:00:00.000000Z",
    finished_at: "2026-09-23T08:00:01.000000Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listOperations.mockResolvedValue([]);
  useChatUiStore.setState({ turnExecuted: null });
});

describe("ChatExecutedOperationCard", () => {
  it("会话无直执行记录时不渲染", () => {
    const { container } = renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("呈现直执行回执的授权依据与结果入口", async () => {
    listOperations.mockResolvedValue([operationFixture()]);
    renderWithQuery(<ChatExecutedOperationCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("已自动执行")).toBeVisible();
    // 授权依据：当时档位 + 触发指令摘录（spec 用户故事 7）。
    expect(screen.getByText("授权依据：帮我批准")).toBeVisible();
    expect(screen.getByText("触发指令：「帮我建一门物理课」")).toBeVisible();
    expect(screen.getByText("创建课程")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开课程" });
    expect(link).toHaveAttribute("href", "/spaces/$courseId");
  });

  it("确认路径回写的 operation（proposal_id 非空）不进本卡", async () => {
    listOperations.mockResolvedValue([
      operationFixture({ proposal_id: "p-1", id: "op-confirmed" }),
    ]);
    const { container } = renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} />,
    );
    await waitFor(() =>
      expect(listOperations).toHaveBeenCalledWith({ session_id: SESSION_ID }),
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("失败回执呈现稳定错误码", async () => {
    listOperations.mockResolvedValue([
      operationFixture({
        status: "FAILED",
        result: null,
        error_code: "COURSE_DUPLICATE_NAME",
        finished_at: null,
      }),
    ]);
    renderWithQuery(<ChatExecutedOperationCard sessionId={SESSION_ID} />);

    await screen.findByText("创建课程");
    expect(
      screen.getByText(/执行未完成（.+）/, { exact: false }),
    ).toBeInTheDocument();
  });

  it("本轮有执行而查询缺席时降级「历史已清理」占位", async () => {
    useChatUiStore.setState({
      turnExecuted: {
        sessionId: SESSION_ID,
        operations: [
          {
            operationId: "op-gone",
            action: "create_course",
            level: "L1",
            authMode: "FULL_ACCESS",
            payload: {},
            result: { course_id: "c-1" },
          },
        ],
      },
    });
    renderWithQuery(<ChatExecutedOperationCard sessionId={SESSION_ID} />);

    expect(
      await screen.findByText("另有 1 条回执的历史已被清理。"),
    ).toBeVisible();
  });
});
