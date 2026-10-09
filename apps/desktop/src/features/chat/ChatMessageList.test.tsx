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

/** jsdom 无真实布局，用手动触发回调的假观察器驱动「内容增高」事件。 */
class ControllableResizeObserver {
  static instances: ControllableResizeObserver[] = [];
  readonly callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    ControllableResizeObserver.instances.push(this);
  }
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): ResizeObserverEntry[] {
    return [];
  }
}

describe("ChatMessageList 跟随底部（切回会话恢复，10-09 修复）", () => {
  it("内容异步增高（代码高亮 / 过程卡增长）钉住底部；上滚阅读不抢位置", () => {
    const originalObserver = window.ResizeObserver;
    window.ResizeObserver =
      ControllableResizeObserver as unknown as typeof ResizeObserver;
    try {
      const process = responseProcess();
      const view = renderWithQuery(
        <ChatMessageList
          {...BASE}
          messages={[userWithProcess()]}
          streamingText="开始"
          responseProcess={process}
          isStreaming
        />,
      );
      const scroll = screen.getByLabelText("对话消息");
      Object.defineProperties(scroll, {
        scrollHeight: { value: 1000, configurable: true },
        clientHeight: { value: 400, configurable: true },
      });
      const fireGrowth = () => {
        for (const observer of ControllableResizeObserver.instances) {
          observer.callback([], observer as unknown as ResizeObserver);
        }
      };
      // 挂载（切回会话）即到底。
      fireGrowth();
      expect(scroll.scrollTop).toBe(1000);
      // 用户上滚阅读旧消息。
      scroll.scrollTop = 100;
      fireEvent.scroll(scroll);
      // 过程卡条目增多等异步增高不改变消息数与流式文本：仍不抢滚动位置。
      view.rerender(
        <QueryClientProvider client={view.queryClient}>
          <ChatMessageList
            {...BASE}
            messages={[userWithProcess()]}
            streamingText="开始"
            responseProcess={process}
            isStreaming
          />
        </QueryClientProvider>,
      );
      fireGrowth();
      expect(scroll.scrollTop).toBe(100);
      // 回到最新后恢复跟随。
      fireEvent.click(screen.getByRole("button", { name: "回到最新" }));
      expect(scroll.scrollTop).toBe(1000);
      fireGrowth();
      expect(scroll.scrollTop).toBe(1000);
    } finally {
      window.ResizeObserver = originalObserver;
      ControllableResizeObserver.instances.length = 0;
    }
  });
});

describe("ChatMessageList 过程行展示（10-06 追加修复）", () => {
  it("展开过程后每条文案只出现一次，点击行原地展开不再产生第二份", () => {
    const entries: NonNullable<ChatResponseProcess["entries"]> = [
      {
        kind: "tool",
        id: "call-1",
        tool: "search_courses",
        query: "Agent 论文精读",
        status: "SUCCEEDED",
        hits: 1,
      },
      {
        kind: "tool",
        id: "call-2",
        tool: "list_course_records",
        query: "",
        status: "SUCCEEDED",
        hits: null,
      },
    ];
    const process = { ...responseProcess("COMPLETED"), entries };
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess(process)]}
        streamingText={null}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /已完成.*2 次工具调用/ }),
    );
    const list = screen.getByRole("list", { name: "回答过程详情" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getAllByText("「Agent 论文精读」找到 1 门课程")).toHaveLength(
      1,
    );
    expect(
      screen.getAllByText("工具调用：list_course_records · 执行完成"),
    ).toHaveLength(1);

    const row = screen.getByRole("button", {
      name: "「Agent 论文精读」找到 1 门课程",
    });
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("「Agent 论文精读」找到 1 门课程")).toHaveLength(
      1,
    );
  });

  it("完全相同的思考文本只保留一条；相同文案的工具行不去重", () => {
    const entries: NonNullable<ChatResponseProcess["entries"]> = [
      { kind: "commentary", id: "seg-1", text: "先核对课程资料。" },
      { kind: "commentary", id: "seg-2", text: "先核对课程资料。" },
      { kind: "commentary", id: "seg-3", text: "保存记录。" },
      {
        kind: "tool",
        id: "call-1",
        tool: "list_course_records",
        query: "",
        status: "SUCCEEDED",
        hits: null,
      },
      {
        kind: "tool",
        id: "call-2",
        tool: "list_course_records",
        query: "",
        status: "SUCCEEDED",
        hits: null,
      },
    ];
    const process = { ...responseProcess("COMPLETED"), entries };
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[userWithProcess(process)]}
        streamingText={null}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /已完成.*2 次工具调用/ }),
    );
    expect(screen.getAllByText("先核对课程资料。")).toHaveLength(1);
    expect(screen.getByText("保存记录。")).toBeVisible();
    expect(
      screen.getAllByText("工具调用：list_course_records · 执行完成"),
    ).toHaveLength(2);
    expect(
      within(screen.getByRole("list", { name: "回答过程详情" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(4);
  });
});

describe("ChatMessageList — 终态轮次部分输出（规格 §5/§15 成果恢复入口）", () => {
  it("取消轮次按轮次引用展示已持久化部分正文与原因", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[
          {
            ...userWithProcess(),
            turn: {
              id: "turn-1",
              status: "CANCELLED",
              output_text: "已生成的一半",
              result: null,
            },
          },
        ]}
        streamingText={null}
      />,
    );
    expect(
      screen.getByText("回答已停止，以下是已生成的部分内容"),
    ).toBeVisible();
    expect(screen.getByText("已生成的一半")).toBeVisible();
  });

  it("完成轮次（正文以最终消息为准）不渲染部分输出块", () => {
    renderWithQuery(
      <ChatMessageList
        {...BASE}
        messages={[
          {
            ...userWithProcess(),
            turn: {
              id: "turn-2",
              status: "COMPLETED",
              output_text: "",
              result: null,
            },
          },
        ]}
        streamingText={null}
      />,
    );
    expect(screen.queryByText("回答已停止，以下是已生成的部分内容")).toBeNull();
  });
});
