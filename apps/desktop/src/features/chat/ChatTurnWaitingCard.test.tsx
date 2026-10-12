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
