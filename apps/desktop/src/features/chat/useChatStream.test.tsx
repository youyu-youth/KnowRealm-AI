// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { libraryKeys } from "@/features/library/api/keys";
import { useChatStream } from "./useChatStream";

const { streamMessage } = vi.hoisted(() => ({ streamMessage: vi.fn() }));

vi.mock("@/features/chat/api/chatSessions", () => ({
  chatApi: { streamMessage },
}));

type StreamHandlers = {
  onStatus: () => void;
  onToken: (text: string) => void;
  onToolCall: (payload: { tool: string; query: string }) => void;
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
  return { invalidate };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useChatStream 提案查询失效", () => {
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
