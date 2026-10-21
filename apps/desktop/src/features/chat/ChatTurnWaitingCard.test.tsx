// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import type { ChatTurn } from "@/features/chat/api/types";
import { ChatTurnWaitingCard } from "@/features/chat/ChatTurnWaitingCard";

const waitingTurn: ChatTurn = {
  id: "turn-1",
  session_id: "session-1",
  user_message_id: "message-1",
  status: "WAITING_JOB",
  cancel_requested: false,
  attempt: 1,
  output_revision: 1,
  last_seq: 2,
  compacted_seq: 0,
  output_text: "",
  created_at: "2026-10-11T10:00:00Z",
  updated_at: "2026-10-11T10:00:01Z",
  waiting_reason: { kind: "BACKGROUND_TASK" },
  background_tasks: [
    {
      target_type: "RUN",
      target_id: "run-1",
      status: "WAITING_JOB",
      control_scope: "EXCLUSIVE",
    },
  ],
};

describe("ChatTurnWaitingCard 后台等待", () => {
  it("两个不确定分支可分别重试，接受部分结果仍覆盖全部", () => {
    const resume = vi.fn();
    renderWithQuery(
      <ChatTurnWaitingCard
        turn={{
          ...waitingTurn,
          status: "WAITING_USER",
          waiting_reason: {
            kind: "DELEGATION_UNCERTAIN",
            snapshot_id: "snapshot-two",
            delegations: ["child-A", "child-B"].map((execution_id) => ({
              execution_id,
              execution_attempt: 1,
              request_ids: [`request-${execution_id}`],
            })),
          },
        }}
        onResume={resume}
        onStop={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "重试任务 child-B" }));
    expect(resume).toHaveBeenLastCalledWith("RETRY_DELEGATIONS", ["child-B"]);
    fireEvent.click(screen.getByRole("button", { name: "接受已有结果" }));
    expect(resume).toHaveBeenLastCalledWith("ACCEPT_PARTIAL");
  });
  it("不确定请求展示两种明确决定，不沿用普通继续", () => {
    const resume = vi.fn();
    renderWithQuery(
      <ChatTurnWaitingCard
        turn={{
          ...waitingTurn,
          status: "WAITING_USER",
          background_tasks: [
            {
              target_type: "JOB",
              target_id: "job-A",
              status: "COMPLETED",
              control_scope: "EXCLUSIVE",
              execution_id: "child-A",
              agent_id: "knowledge",
              execution_attempt: 1,
            },
            {
              target_type: "JOB",
              target_id: "job-B",
              status: "INTERRUPTED",
              control_scope: "EXCLUSIVE",
              execution_id: "child-B",
              agent_id: "knowledge",
              execution_attempt: 1,
            },
          ],
          waiting_reason: {
            kind: "DELEGATION_UNCERTAIN",
            snapshot_id: "snapshot-1",
            delegations: [
              {
                execution_id: "child-B",
                execution_attempt: 1,
                request_ids: ["request-B"],
              },
            ],
          },
        }}
        onResume={resume}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText(/重试可能再次计费/)).toBeInTheDocument();
    const tasks = screen.getByRole("list", { name: "关联后台任务" });
    expect(tasks).toHaveTextContent("已完成");
    expect(tasks).toHaveTextContent("等待选择");
    expect(tasks).toHaveTextContent("child-A");
    expect(tasks).toHaveTextContent("child-B");
    expect(
      screen.queryByRole("button", { name: "继续生成" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试知识任务" }));
    expect(resume).toHaveBeenLastCalledWith("RETRY_DELEGATIONS");
    fireEvent.click(screen.getByRole("button", { name: "接受已有结果" }));
    expect(resume).toHaveBeenLastCalledWith("ACCEPT_PARTIAL");
  });
  it("明确说明压缩继续会追加四次请求且不批准业务操作", () => {
    const resume = vi.fn();
    renderWithQuery(
      <ChatTurnWaitingCard
        turn={{
          ...waitingTurn,
          status: "WAITING_USER",
          waiting_reason: { kind: "CONTEXT_COMPACTION_LIMIT" },
        }}
        onResume={resume}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText(/不批准业务操作/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "继续压缩（追加四次请求）" }),
    );
    expect(resume).toHaveBeenCalledOnce();
  });
  it("显示真实任务状态、自动接续文案和停止入口", () => {
    const stop = vi.fn();
    renderWithQuery(
      <ChatTurnWaitingCard
        turn={waitingTurn}
        onResume={vi.fn()}
        onStop={stop}
      />,
    );
    expect(screen.getByText(/完成后自动继续回答/)).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "关联后台任务" }),
    ).toHaveTextContent("等待后台处理");
    expect(
      screen.queryByRole("button", { name: "继续生成" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "停止本轮" }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it("停止已受理时禁止重复提交控制", () => {
    renderWithQuery(
      <ChatTurnWaitingCard
        turn={{ ...waitingTurn, cancel_requested: true }}
        onResume={vi.fn()}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "停止本轮" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "停止本轮" })).toHaveTextContent(
      "正在停止",
    );
  });
});
