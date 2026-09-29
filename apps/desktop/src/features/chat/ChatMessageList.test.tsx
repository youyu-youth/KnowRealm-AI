// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import type { ChatMessage } from "@/features/chat/api/types";

/** 保存知识点对话框与本测试无关：mount 即安（saveTarget 恒 null 不打开）。 */
vi.mock("@/features/chat/SaveKnowledgePointDialog", () => ({
  SaveKnowledgePointDialog: () => null,
}));

const BASE = {
  sessionId: "session-1",
  toolActivities: [],
  isStreaming: false,
  streamError: null,
  onRetry: () => {},
  defaultRecordId: null,
};

function assistantMessage(content: string): ChatMessage {
  return {
    id: "m-1",
    session_id: "session-1",
    role: "ASSISTANT",
    content,
    citations: [],
    model: "test",
    token_usage: null,
    created_at: "2026-09-29T10:00:00.000000Z",
  } as ChatMessage;
}

const DRAFT_JSON = `{"goal_id":"90000000-0000-4000-8000-000000000001","phases":[{"title":"第一阶段","items":[{"action_type":"CUSTOM","content":"任务 1","estimated_minutes":60,"reason":"理由","record_id":null,"concept_id":null,"scheduled_date":"2026-09-29"},{"action_type":"CUSTOM","content":"任务 2","estimated_minutes":30,"reason":"理由","record_id":null,"concept_id":null,"scheduled_date":"2026-09-30"}]}]}`;

describe("ChatMessageList — 计划草案 JSON 正文兜底（工单 02 真机验收修复）", () => {
  it("正文整体是草案 JSON 时渲染折叠块而非裸 JSON", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[assistantMessage(DRAFT_JSON)]}
        streamingText={null}
      />,
    );
    expect(
      screen.getByText(
        "AI 返回了学习计划草案的结构化数据（共 2 项，未生效）。",
      ),
    ).toBeVisible();
    expect(
      screen.getByText(
        "这条回复没有生成确认卡；如需生成学习计划，请在对话中重新发起请求。",
      ),
    ).toBeVisible();
    expect(screen.getByText("查看原始数据")).toBeVisible();
    // 裸 JSON 收起在 details 内：在 DOM 但默认不可见（不裸奔）。
    expect(screen.getByText(/\"phases\"/)).not.toBeVisible();
  });

  it("前导 JSON + 中文复述的混合形态：剥掉 JSON 只渲染中文（真机二轮修复）", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[
          assistantMessage(
            `${DRAFT_JSON}\n已按目标「redis基础学习」生成计划草案，共 5 个阶段、38 项，请过目。`,
          ),
        ]}
        streamingText={null}
      />,
    );
    // 中文复述正常渲染。
    expect(
      screen.getByText(/已按目标「redis基础学习」生成计划草案/),
    ).toBeInTheDocument();
    // 前导 JSON 不出现在渲染结果中。
    expect(screen.queryByText(/\"phases\"/)).not.toBeInTheDocument();
    // 混合形态不出现折叠块入口。
    expect(screen.queryByText("查看原始数据")).not.toBeInTheDocument();
  });

  it("正常中文正文照常渲染（不走折叠块）", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[
          assistantMessage("我为你制定了四周计划，第一阶段先打基础。"),
        ]}
        streamingText={null}
      />,
    );
    expect(
      screen.getByText("我为你制定了四周计划，第一阶段先打基础。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("查看原始数据")).not.toBeInTheDocument();
  });

  it("流式文本以 JSON 起势时显示占位态而非滚动裸 JSON", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[]}
        streamingText={'{"phases":[{"title":"第一'}
        isStreaming
      />,
    );
    expect(screen.getByText("正在准备结构化数据…")).toBeVisible();
    expect(screen.queryByText(/phases/)).not.toBeInTheDocument();
  });
});
