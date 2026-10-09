// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { libraryKeys } from "@/features/library/api/keys";
import type { ChatResponseProcess, ChatTurn } from "./api/types";
import { useChatTurns } from "./useChatTurns";

const { chatApi } = vi.hoisted(() => ({
  chatApi: {
    submitTurn: vi.fn(),
    turnEvents: vi.fn(),
    getTurn: vi.fn(),
    activeTurn: vi.fn(),
    cancelTurn: vi.fn(),
  },
}));

vi.mock("@/features/chat/api/chatSessions", () => ({ chatApi }));

type StreamHandlers = {
  onStatus: (payload: { phase: string; process?: ChatResponseProcess }) => void;
  onToken: (text: string, segmentId?: string) => void;
  onToolCall: (payload: {
    tool: string;
    query: string;
    segmentId?: string;
    process?: ChatResponseProcess;
  }) => void;
  onToolResult: (payload: { hits: number; ok: boolean }) => void;
  onDone: (payload: Record<string, unknown>) => void;
  onError: (payload: { code: string; detail: string }) => void;
};

// 全部流结束路径（done / error / 断开）都要失效提案查询：
// 断线后已落库的提案经查询恢复（工单 02 review 先例）。
const PROPOSALS_KEY = [...libraryKeys.all, "proposals"];

const TURN_ID = "turn-1";

function turnSnapshot(overrides: Partial<ChatTurn> = {}): ChatTurn {
  return {
    id: TURN_ID,
    session_id: "s-1",
    user_message_id: "u-1",
    final_message_id: null,
    status: "RUNNING",
    cancel_requested: false,
    attempt: 1,
    output_revision: 1,
    last_seq: 0,
    error_code: null,
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    started_at: null,
    finished_at: null,
    output_text: "",
    process: null,
    ...overrides,
  } as ChatTurn;
}

async function setup(impl: (handlers: StreamHandlers) => Promise<void>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  chatApi.activeTurn.mockResolvedValue(null);
  chatApi.submitTurn.mockResolvedValue(turnSnapshot());
  // 默认快照在途：断线重连测试按需覆盖为终态。
  chatApi.getTurn.mockResolvedValue(turnSnapshot());
  chatApi.turnEvents.mockImplementation(
    (_turnId: string, _afterSeq: number, handlers: StreamHandlers) =>
      impl(handlers),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useChatTurns("s-1"), { wrapper });
  await act(async () => {
    await result.current.send("你好", false);
  });
  return { invalidate, result };
}

beforeEach(() => {
  // resetAllMocks 连实现一起清：对账/快照 mock 不跨用例泄漏。
  vi.resetAllMocks();
});

describe("useChatTurns 订阅与失效", () => {
  it("工具调用前的正文段移出正文；断开时工具态转 INTERRUPTED", async () => {
    let handlers: StreamHandlers | undefined;
    let finish: (() => void) | undefined;
    const { result } = await setup((callbacks) => {
      handlers = callbacks;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    act(() => handlers?.onToken("先核对时间。", "segment-1"));
    expect(result.current.streamedText).toBe("先核对时间。");
    act(() => {
      handlers?.onToolCall({
        tool: "get_current_time",
        query: "",
        segmentId: "segment-1",
        process: {
          id: "p-1",
          session_id: "s-1",
          user_message_id: "u-1",
          assistant_message_id: null,
          status: "RUNNING",
          started_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ended_at: null,
          elapsed_ms: 0,
          history_saved: true,
          entries: [
            {
              kind: "tool",
              id: "call-1",
              tool: "get_current_time",
              query: "",
              status: "RUNNING",
              hits: null,
            },
          ],
        },
      });
      handlers?.onToken("当前时间已经核对。", "segment-2");
    });
    expect(result.current.streamedText).toBe("当前时间已经核对。");
    // 连接断开（未再见终态）：钩子按快照对账；快照返回 INTERRUPTED 时过程收口。
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({
        status: "INTERRUPTED",
        output_text: "当前时间已经核对。",
        process: {
          id: "p-1",
          session_id: "s-1",
          user_message_id: "u-1",
          assistant_message_id: null,
          status: "INTERRUPTED",
          started_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ended_at: new Date().toISOString(),
          elapsed_ms: 100,
          history_saved: true,
          entries: [
            {
              kind: "tool",
              id: "call-1",
              tool: "get_current_time",
              query: "",
              status: "INTERRUPTED",
              hits: null,
            },
          ],
        },
      }),
    );
    await act(async () => finish?.());
    await waitFor(() => {
      expect(result.current.responseProcess?.entries?.[0]).toMatchObject({
        status: "INTERRUPTED",
      });
    });
  });

  it("done 后失效提案查询并清除在途态", async () => {
    const { invalidate, result } = await setup(
      (handlers) =>
        new Promise((resolve) => {
          handlers.onDone({ content: "最终回答", memoryUsed: [] });
          resolve();
        }),
    );
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: PROPOSALS_KEY }),
      );
      expect(result.current.isStreaming).toBe(false);
    });
  });

  it("error 事件后失效提案查询（提案可能已落库）", async () => {
    const { invalidate } = await setup(
      (handlers) =>
        new Promise((resolve) => {
          handlers.onError({ code: "INTERNAL_ERROR", detail: "出错了" });
          resolve();
        }),
    );
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: PROPOSALS_KEY }),
      );
    });
  });

  it("订阅断开（非用户中止）后快照对账收尾并失效提案查询", async () => {
    const { invalidate } = await setup(() =>
      Promise.reject(
        Object.assign(new Error("aborted"), { name: "AbortError" }),
      ),
    );
    // 快照对账发现终态失败：错误呈现 + 提案查询失效（断线前可能已落库）。
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({
        status: "FAILED",
        error_message: "回答生成失败，请稍后重试",
      }),
    );
    await waitFor(
      () => {
        expect(invalidate).toHaveBeenCalledWith(
          expect.objectContaining({ queryKey: PROPOSALS_KEY }),
        );
      },
      { timeout: 4000 },
    );
  });
});

describe("useChatTurns 停止与会话恢复", () => {
  it("停止发持久取消指令，不 abort 订阅连接", async () => {
    let finish: (() => void) | undefined;
    const { result } = await setup(
      (handlers) =>
        new Promise((resolve) => {
          finish = () => {
            handlers.onStatus({ phase: "cancelled" });
            resolve();
          };
        }),
    );
    expect(result.current.isStreaming).toBe(true);
    chatApi.cancelTurn.mockResolvedValue({
      turn: turnSnapshot({ cancel_requested: true }),
    });
    act(() => result.current.stop());
    await waitFor(() => {
      expect(chatApi.cancelTurn).toHaveBeenCalledWith(TURN_ID);
      expect(result.current.stopping).toBe(true);
    });
    await act(async () => finish?.());
  });

  it("受理未确认（网络失败）保留 request_id：重试携带同一身份", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    chatApi.activeTurn.mockResolvedValue(null);
    const submitCalls: string[] = [];
    chatApi.submitTurn.mockImplementation(
      async (_sid: string, body: { requestId: string }) => {
        submitCalls.push(body.requestId);
        if (submitCalls.length === 1) throw new TypeError("fetch failed");
        return turnSnapshot();
      },
    );
    chatApi.turnEvents.mockResolvedValue(undefined);
    chatApi.getTurn.mockResolvedValue(turnSnapshot());
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurns("s-1"), { wrapper });
    await act(async () => {
      await result.current.send("网络抖动问题", false);
    });
    expect(result.current.streamError).toBe("fetch failed");
    await act(async () => {
      await result.current.send("网络抖动问题", false);
    });
    expect(submitCalls).toHaveLength(2);
    expect(submitCalls[0]).toBe(submitCalls[1]);
  });

  it("断线重连以快照正文为基准重置本地拼接，再从游标续订", async () => {
    let attempt = 0;
    const { result } = await setup(
      () =>
        new Promise<void>((resolve) => {
          attempt += 1;
          if (attempt === 1) {
            // 第一次订阅被网络中断（非用户中止、无终态）。
            throw Object.assign(new Error("network down"), {
              name: "NetworkError",
            });
          }
          resolve();
        }),
    );
    // 快照对账：在途 + 已推进到 5，正文=服务端权威基准。
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({ last_seq: 5, output_text: "快照基准正文" }),
    );
    await waitFor(
      () => {
        expect(result.current.streamedText).toBe("快照基准正文");
      },
      { timeout: 4000 },
    );
    // 续订从快照 last_seq 开始（缺口不重放，规格 §5）。
    await waitFor(() => {
      expect(chatApi.turnEvents).toHaveBeenLastCalledWith(
        TURN_ID,
        5,
        expect.anything(),
        expect.anything(),
      );
    });
  });

  it("打开会话时恢复在途轮次：快照正文与过程先落地，再从游标续订", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    chatApi.activeTurn.mockResolvedValue(
      turnSnapshot({
        last_seq: 3,
        output_text: "恢复前的部分输出",
      }),
    );
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({
        last_seq: 3,
        output_text: "恢复前的部分输出",
      }),
    );
    chatApi.turnEvents.mockResolvedValue(undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurns("s-1"), { wrapper });
    await waitFor(() => {
      expect(result.current.isStreaming).toBe(true);
      expect(result.current.streamedText).toBe("恢复前的部分输出");
    });
    expect(chatApi.turnEvents).toHaveBeenCalledWith(
      TURN_ID,
      3,
      expect.anything(),
      expect.anything(),
    );
  });

  it("恢复快照后继续收 token：正文追加在快照基准之后而非覆盖", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    let handlers: StreamHandlers | undefined;
    chatApi.activeTurn.mockResolvedValue(
      turnSnapshot({ last_seq: 7, output_text: "prefix" }),
    );
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({ last_seq: 7, output_text: "prefix" }),
    );
    chatApi.turnEvents.mockImplementation(
      (_turnId: string, afterSeq: number, next: StreamHandlers) => {
        // 只接本用例 hook 的订阅（游标 7）：其它用例卸载后可能补一次调用。
        if (afterSeq !== 7) return new Promise<void>(() => {});
        handlers = next;
        return new Promise<void>(() => {});
      },
    );
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurns("s-1"), { wrapper });
    await waitFor(() => {
      expect(result.current.streamedText).toBe("prefix");
      expect(handlers).toBeDefined();
    });
    // 快照是权威基准（规格 §5）：从 last_seq 续订的 token 只能追加在它之后。
    act(() => handlers?.onToken("suffix", "segment-1"));
    expect(result.current.streamedText).toBe("prefixsuffix");
  });

  it("断线重连恢复快照后继续收 token：正文追加在快照基准之后而非覆盖", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    let rejectedOnce = false;
    let handlers: StreamHandlers | undefined;
    chatApi.activeTurn.mockResolvedValue(
      turnSnapshot({ last_seq: 7, output_text: "prefix" }),
    );
    chatApi.getTurn.mockResolvedValue(
      turnSnapshot({ last_seq: 7, output_text: "prefix" }),
    );
    chatApi.turnEvents.mockImplementation(
      (_turnId: string, afterSeq: number, next: StreamHandlers) => {
        // 只接本用例 hook 的订阅（游标 7）：其它用例卸载后可能补一次调用。
        if (afterSeq !== 7) return new Promise<void>(() => {});
        if (!rejectedOnce) {
          // 第一次订阅被网络中断（非用户中止、无终态）→ 走快照对账重连。
          rejectedOnce = true;
          return Promise.reject(
            Object.assign(new Error("network down"), { name: "NetworkError" }),
          );
        }
        handlers = next;
        return new Promise<void>(() => {});
      },
    );
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurns("s-1"), { wrapper });
    await waitFor(
      () => {
        expect(result.current.streamedText).toBe("prefix");
        expect(handlers).toBeDefined();
      },
      { timeout: 4000 },
    );
    expect(chatApi.turnEvents).toHaveBeenCalledWith(
      TURN_ID,
      7,
      expect.anything(),
      expect.anything(),
    );
    act(() => handlers?.onToken("suffix", "segment-1"));
    expect(result.current.streamedText).toBe("prefixsuffix");
  });
});
