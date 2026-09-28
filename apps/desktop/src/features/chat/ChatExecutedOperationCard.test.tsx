// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatExecutedOperationCard } from "./ChatExecutedOperationCard";

const { listOperations, undoOperation, retryOperation } = vi.hoisted(() => ({
  listOperations: vi.fn(),
  undoOperation: vi.fn(),
  retryOperation: vi.fn(),
}));

vi.mock("@/features/settings/api/operationHistory", () => ({
  operationHistoryApi: { listOperations, undoOperation, retryOperation },
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
    undoable: boolean;
    undo_reason: string | null;
    undone_by: string | null;
    undo_of: string | null;
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
    undoable: false,
    undo_reason: null,
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
});

describe("ChatExecutedOperationCard", () => {
  it("消息流无锚点时不渲染、不发查询", () => {
    const { container } = renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} anchorIds={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(listOperations).not.toHaveBeenCalled();
  });

  it("查询失败不渲染：网络失败≠历史已清理，不误报占位", async () => {
    listOperations.mockRejectedValue(new Error("网络异常"));
    const { container } = renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} anchorIds={["op-1"]} />,
    );
    await waitFor(() => expect(listOperations).toHaveBeenCalled());
    // 失败定局后仍无卡、无「历史已清理」。
    expect(container).toBeEmptyDOMElement();
  });

  it("锚点命中查询时呈现授权依据与结果入口", async () => {
    listOperations.mockResolvedValue([operationFixture()]);
    renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} anchorIds={["op-1"]} />,
    );

    expect(await screen.findByText("已自动执行")).toBeVisible();
    // 授权依据：当时档位 + 触发指令摘录（spec 用户故事 7）；查询异步到位，
    // 用 findBy 等待（锚点驱动的卡片先渲染壳、详情随后填充）。
    expect(await screen.findByText("授权依据：帮我批准")).toBeVisible();
    expect(
      await screen.findByText("触发指令：「帮我建一门物理课」"),
    ).toBeVisible();
    expect(screen.getByText("创建课程")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开课程" });
    expect(link).toHaveAttribute("href", "/spaces/$courseId");
    // 请求页大小按锚点数取（默认下限 50）。
    expect(listOperations).toHaveBeenCalledWith({
      session_id: SESSION_ID,
      limit: 50,
    });
  });

  it("锚点超默认页大小时按锚点数请求", async () => {
    const many = Array.from({ length: 80 }, (_, index) =>
      operationFixture({ id: `op-${index}` }),
    );
    listOperations.mockResolvedValue(many);
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={many.map((operation) => operation.id)}
      />,
    );

    expect(listOperations).toHaveBeenCalledWith({
      session_id: SESSION_ID,
      limit: 80,
    });
    expect(await screen.findAllByText("创建课程")).toHaveLength(80);
  });

  it("查询有数据但锚点缺席（确认路径回写）不进本卡", async () => {
    listOperations.mockResolvedValue([
      operationFixture({ proposal_id: "p-1", id: "op-confirmed" }),
    ]);
    const { container } = renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} anchorIds={[]} />,
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
    renderWithQuery(
      <ChatExecutedOperationCard sessionId={SESSION_ID} anchorIds={["op-1"]} />,
    );

    await screen.findByText("创建课程");
    expect(
      screen.getByText(/执行未完成（.+）/, { exact: false }),
    ).toBeInTheDocument();
  });

  it("锚点在而查询缺席时降级「历史已清理」占位（跨重启持久锚点）", async () => {
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={["op-gone"]}
      />,
    );

    expect(
      await screen.findByText("另有 1 条回执的历史已被清理。"),
    ).toBeVisible();
  });

  it("部分清理：命中锚点渲染回执、缺席锚点计占位", async () => {
    listOperations.mockResolvedValue([operationFixture()]);
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={["op-1", "op-gone"]}
      />,
    );

    expect(await screen.findByText("创建课程")).toBeVisible();
    expect(screen.getByText("另有 1 条回执的历史已被清理。")).toBeVisible();
  });

  it("满页（可能截断）时缺席锚点不计占位：宁缺勿错报", async () => {
    // 锚点 51 个、limit 按锚点数取 51，查询回满页 51 条但 op-gone 不在其中；
    // 满页=可能仍有未取页，「未取到」不判定为「已清理」。
    const anchorIds = [
      "op-gone",
      ...Array.from({ length: 50 }, (_, i) => `op-${i}`),
    ];
    listOperations.mockResolvedValue(
      Array.from({ length: 51 }, (_, index) =>
        operationFixture({ id: `op-${index}` }),
      ),
    );
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={anchorIds}
      />,
    );

    await waitFor(() =>
      expect(listOperations).toHaveBeenCalledWith({
        session_id: SESSION_ID,
        limit: 51,
      }),
    );
    expect(await screen.findAllByText("创建课程")).toHaveLength(50);
    expect(screen.queryByText(/历史已被清理/)).not.toBeInTheDocument();
  });

  it("可撤销的成功行呈现撤销按钮，点击调撤销端点（工单 06）", async () => {
    listOperations.mockResolvedValue([
      operationFixture({ id: "op-undoable", undoable: true }),
    ]);
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={["op-undoable"]}
      />,
    );

    const undoButton = await screen.findByRole("button", { name: /撤销/ });
    expect(undoButton).toBeVisible();
    undoOperation.mockResolvedValue(operationFixture({ id: "comp-1" }));
    fireEvent.click(undoButton);
    await waitFor(() =>
      expect(undoOperation).toHaveBeenCalledWith("op-undoable"),
    );
  });

  it("已撤销行显示标记不显示按钮；不可撤销行无按钮；失败行呈现重试", async () => {
    listOperations.mockResolvedValue([
      operationFixture({
        id: "op-undone",
        undoable: true,
        undone_by: "comp-1",
      }),
      operationFixture({ id: "op-plain", undoable: false }),
      operationFixture({
        id: "op-failed",
        status: "FAILED",
        result: null,
        error_code: "COURSE_DUPLICATE_NAME",
        finished_at: null,
      }),
    ]);
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={["op-undone", "op-plain", "op-failed"]}
      />,
    );

    expect(await screen.findByText("该操作已撤销。")).toBeVisible();
    // 仅失败行有重试按钮（撤销按钮不出现：已撤销 / 不可撤销 / 失败态均无）。
    const retryButton = screen.getByRole("button", { name: /重试/ });
    expect(
      screen.queryByRole("button", { name: /^撤销$/ }),
    ).not.toBeInTheDocument();
    retryOperation.mockResolvedValue(
      operationFixture({ id: "op-failed", status: "SUCCEEDED" }),
    );
    fireEvent.click(retryButton);
    await waitFor(() =>
      expect(retryOperation).toHaveBeenCalledWith("op-failed"),
    );
  });

  it("不可撤销行就地呈现原因（spec 用户故事 28，review P2）", async () => {
    listOperations.mockResolvedValue([
      operationFixture({
        id: "op-delete",
        action: "delete_course",
        undoable: false,
        undo_reason:
          "课程删除（含级联删除记录）不可撤销：影响面大且暂无恢复入口",
      }),
    ]);
    renderWithQuery(
      <ChatExecutedOperationCard
        sessionId={SESSION_ID}
        anchorIds={["op-delete"]}
      />,
    );

    expect(
      await screen.findByText(
        "不可撤销：课程删除（含级联删除记录）不可撤销：影响面大且暂无恢复入口",
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /^撤销$/ }),
    ).not.toBeInTheDocument();
  });
});
