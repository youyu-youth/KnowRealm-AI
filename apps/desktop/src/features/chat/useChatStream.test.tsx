// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { libraryKeys } from "@/features/library/api/keys";
import type { ChatResponseProcess } from "./api/types";
import { useChatStream } from "./useChatStream";

const { streamMessage } = vi.hoisted(() => ({ streamMessage: vi.fn() }));

vi.mock("@/features/chat/api/chatSessions", () => ({
  chatApi: { streamMessage },
}));

type StreamHandlers = {
  onStatus: () => void;
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

// 全部流结束路径（done / SSE error / 停止 / 断开）都要失效提案查询：
// 断线后已落库的提案经查询恢复（工单 02 review）。
const PROPOSALS_KEY = [...libraryKeys.all, "proposals"];

async function setup(impl: (handlers: StreamHandlers) => Promise<void>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  streamMessage.mockImplementation(
    (_sessionId: string, _content: string, handlers: StreamHandlers) =>
      impl(handlers),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useChatStream("s-1"), { wrapper });
  await act(async () => {
    result.current.send("你好", false);
  });
  return { invalidate, result };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useChatStream 提案查询失效", () => {
  it("确认工具调用后将公开说明移出正文，断开时停止工具旋转", async () => {
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
    await act(async () => finish?.());
    expect(result.current.responseProcess?.status).toBe("INTERRUPTED");
    expect(result.current.responseProcess?.entries?.[0]).toMatchObject({
      status: "INTERRUPTED",
    });
  });

  it("done 后失效提案查询", async () => {
    const { invalidate } = await setup(
      (handlers) =>
        new Promise((resolve) => {
          handlers.onDone({});
          resolve();
        }),
    );
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: PROPOSALS_KEY }),
      );
    });
  });

  it("SSE error 事件后失效提案查询（提案可能已落库）", async () => {
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

  it("停止/网络断开（AbortError）后失效提案查询", async () => {
    const { invalidate } = await setup(() =>
      Promise.reject(
        Object.assign(new Error("aborted"), { name: "AbortError" }),
      ),
    );
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: PROPOSALS_KEY }),
      );
    });
  });
});
