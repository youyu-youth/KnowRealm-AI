import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { chatApi } from "@/features/chat/api/chatSessions";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

afterEach(() => {
  server.resetHandlers();
});

function sseBody(events: string[], keepOpen = false) {
  const encoder = new TextEncoder();
  let close = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(encoder.encode(event));
      if (!keepOpen) controller.close();
      else close = () => controller.close();
    },
  });
  return { stream, close };
}

describe("chatApi.streamMessage", () => {
  it("按到达顺序逐 token 回调，done 携带完整内容与消息 id", async () => {
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        () => {
          const { stream } = sseBody([
            'event: status\ndata: {"phase":"generating"}\n\n',
            'event: token\ndata: {"text":"操"}\n\n',
            'event: token\ndata: {"text":"作"}\n\n',
            'event: token\ndata: {"text":"系统"}\n\n',
            'event: done\ndata: {"message_id":"m1","content":"操作系统"}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    const tokens: string[] = [];
    let statusCount = 0;
    let donePayload: { messageId: string; content: string } | null = null;
    await chatApi.streamMessage(
      SESSION_ID,
      "什么是操作系统",
      {
        onStatus: () => {
          statusCount += 1;
        },
        onToken: (text) => tokens.push(text),
        onDone: (payload) => {
          donePayload = payload;
        },
        onError: () => {
          throw new Error("不应出现 error 事件");
        },
      },
      undefined,
    );

    expect(statusCount).toBe(1);
    expect(tokens).toEqual(["操", "作", "系统"]);
    expect(donePayload).toEqual({ messageId: "m1", content: "操作系统" });
  });

  it("error 事件回调可读错误码；409 由 apiRequest 转为 ApiError", async () => {
    let rejected = false;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        () => {
          if (!rejected) {
            rejected = true;
            const { stream } = sseBody([
              'event: error\ndata: {"code":"CHAT_STREAM_FAILED","detail":"回答生成失败，请稍后重试"}\n\n',
            ]);
            return new HttpResponse(stream, {
              headers: { "Content-Type": "text/event-stream" },
            });
          }
          return HttpResponse.json(
            { detail: "CHAT_STREAM_IN_PROGRESS：该对话正在生成回答，请稍候" },
            { status: 409 },
          );
        },
      ),
    );

    const errors: { code: string; detail: string }[] = [];
    await chatApi.streamMessage(
      SESSION_ID,
      "提问",
      {
        onStatus: () => undefined,
        onToken: () => undefined,
        onDone: () => undefined,
        onError: (payload) => errors.push(payload),
      },
      undefined,
    );
    expect(errors).toEqual([
      { code: "CHAT_STREAM_FAILED", detail: "回答生成失败，请稍后重试" },
    ]);

    await expect(
      chatApi.streamMessage(
        SESSION_ID,
        "再问",
        {
          onStatus: () => undefined,
          onToken: () => undefined,
          onDone: () => undefined,
          onError: () => undefined,
        },
        undefined,
      ),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("停止信号取消读取并转抛 AbortError", async () => {
    const { stream, close } = sseBody(
      ['event: status\ndata: {"phase":"generating"}\n\n'],
      true,
    );
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        () =>
          new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    const controller = new AbortController();
    const pending = chatApi.streamMessage(
      SESSION_ID,
      "长问题",
      {
        onStatus: () => controller.abort(),
        onToken: () => undefined,
        onDone: () => undefined,
        onError: () => undefined,
      },
      controller.signal,
    );
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    close();
  });
});
