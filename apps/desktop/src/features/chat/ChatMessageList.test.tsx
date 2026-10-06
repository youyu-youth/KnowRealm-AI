// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatMessageList } from "@/features/chat/ChatMessageList";
import type {
  ChatMessage,
  ChatResponseProcess,
} from "@/features/chat/api/types";

/** 保存知识点对话框与本测试无关：mount 即安（saveTarget 恒 null 不打开）。 */
vi.mock("@/features/chat/SaveKnowledgePointDialog", () => ({
  SaveKnowledgePointDialog: () => null,
}));

const BASE = {
  sessionId: "session-1",

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
    expect(screen.getByText(/"phases"/)).not.toBeVisible();
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
    expect(screen.queryByText(/"phases"/)).not.toBeInTheDocument();
    // 混合形态不出现折叠块入口。
    expect(screen.queryByText("查看原始数据")).not.toBeInTheDocument();
  });

  it("中文在前 + JSON 在后（真机三轮形态）：剥掉 JSON 只渲染中文", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[
          assistantMessage(`我先确认目标，再重新生成草案。${DRAFT_JSON}`),
        ]}
        streamingText={null}
      />,
    );
    expect(
      screen.getByText("我先确认目标，再重新生成草案。"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/"phases"/)).not.toBeInTheDocument();
    expect(screen.queryByText("查看原始数据")).not.toBeInTheDocument();
  });

  it("流式中段出现 JSON：前部中文照常渲染、JSON 起点后截断", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[]}
        streamingText={'我先确认目标。{"phases":[{"title":"第一'}
        isStreaming
      />,
    );
    expect(screen.getByText("我先确认目标。")).toBeInTheDocument();
    expect(screen.queryByText(/phases/)).not.toBeInTheDocument();
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

function responseProcess(
  status: ChatResponseProcess["status"] = "RUNNING",
): ChatResponseProcess {
  return {
    id: "process-1",
    session_id: "session-1",
    user_message_id: "user-1",
    assistant_message_id: status === "COMPLETED" ? "m-1" : null,
    started_at: "2026-10-06T00:00:00Z",
    updated_at: "2026-10-06T00:00:18Z",
    ended_at: status === "RUNNING" ? null : "2026-10-06T00:00:18Z",
    status,
    elapsed_ms: 18000,
    history_saved: true,
    entries: Array.from({ length: 12 }, (_, index) => ({
      kind: "tool" as const,
      id: `call-${index}`,
      tool: "search_library",
      query: `查询${index}`,
      status: "SUCCEEDED" as const,
      hits: index,
    })),
  };
}

function userWithProcess(process?: ChatResponseProcess): ChatMessage {
  return {
    ...assistantMessage("讲解 Redis"),
    id: "user-1",
    role: "USER",
    response_processes: process ? [process] : [],
  };
}

describe("ChatMessageList 紧凑过程", () => {
  it("十二次工具调用默认只显示最新一条，手动展开在完成和历史接管后保持", () => {
    const process = responseProcess();
    const view = renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess()]}
        streamingText=""
        responseProcess={process}
        isStreaming
      />,
    );
    expect(screen.getByText("「查询11」命中 11 条")).toBeVisible();
    expect(screen.queryByText("「查询0」命中 0 条")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /12 次工具调用/ }));
    const list = screen.getByRole("list", { name: "回答过程详情" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(12);
    const completed = {
      ...process,
      status: "COMPLETED" as const,
      assistant_message_id: "m-1",
    };
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <ChatMessageList
          {...BASE}
          messages={[userWithProcess(completed), assistantMessage("课程回答")]}
          streamingText={null}
          responseProcess={completed}
        />
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole("button", { name: /已完成.*12 次工具调用/ }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("「查询0」命中 0 条")).toBeVisible();
  });

  it("历史默认收起；失败、中断、待确认及保存不完整均有真实状态", () => {
    const process = responseProcess("INTERRUPTED");
    process.entries = [
      {
        kind: "tool",
        id: "create",
        tool: "create_course",
        query: "Redis",
        status: "AWAITING_CONFIRMATION",
        hits: null,
      },
    ];
    process.history_saved = false;
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess(process)]}
        streamingText={null}
      />,
    );
    const trigger = screen.getByRole("button", {
      name: /回答已中断.*1 次工具调用/,
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("过程历史保存不完整")).toBeVisible();
    fireEvent.click(trigger);
    expect(screen.getByText(/create_course.*Redis.*待确认/)).toBeVisible();
    expect(screen.queryByText(/命中 0 条/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新生成回答" })).toBeVisible();
  });

  it("阅读旧消息时新 token 不抢滚动位置，回到最新后恢复跟随", () => {
    const view = renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess()]}
        streamingText="开始"
        isStreaming
      />,
    );
    const scroll = screen.getByLabelText("对话消息");
    Object.defineProperties(scroll, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 400, configurable: true },
    });
    scroll.scrollTop = 100;
    fireEvent.scroll(scroll);
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <ChatMessageList
          {...BASE}
          messages={[userWithProcess()]}
          streamingText="开始继续"
          isStreaming
        />
      </QueryClientProvider>,
    );
    expect(scroll.scrollTop).toBe(100);
    fireEvent.click(screen.getByRole("button", { name: "回到最新" }));
    expect(scroll.scrollTop).toBe(1000);
  });

  it("普通成功回答不显示空过程入口", () => {
    const process = { ...responseProcess("COMPLETED"), entries: [] };
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess(process), assistantMessage("普通回答")]}
        streamingText={null}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /次工具调用/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("普通回答")).toBeVisible();
  });
});
