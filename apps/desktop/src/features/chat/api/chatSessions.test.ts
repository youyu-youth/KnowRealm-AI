import { http, HttpResponse } from "msw";
import i18next from "i18next";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";
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
        onToolCall: () => undefined,
        onToolResult: () => undefined,
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

  it("tool_call / tool_result 事件按到达顺序分发，畸形载荷忽略", async () => {
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        () => {
          const { stream } = sseBody([
            'event: status\ndata: {"phase":"generating"}\n\n',
            'event: tool_call\ndata: {"tool":"search_transcript","query":"MVCC"}\n\n',
            'event: tool_call\ndata: {"tool":"search_transcript"}\n\n',
            'event: tool_result\ndata: {"tool":"search_transcript","hits":3,"ok":true}\n\n',
            'event: tool_result\ndata: {"tool":"search_transcript","query":"MVCC"}\n\n',
            'event: token\ndata: {"text":"命中"}\n\n',
            'event: tool_call\ndata: {"tool":"search_transcript","query":"undo"}\n\n',
            'event: tool_result\ndata: {"tool":"search_transcript","hits":0,"ok":false}\n\n',
            'event: done\ndata: {"message_id":"m1","content":"命中"}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    const events: string[] = [];
    const tokens: string[] = [];
    await chatApi.streamMessage(
      SESSION_ID,
      "MVCC 怎么实现",
      {
        onStatus: () => events.push("status"),
        onToken: (text) => {
          events.push("token");
          tokens.push(text);
        },
        onToolCall: (payload) =>
          events.push(`tool_call:${payload.tool}:${payload.query}`),
        onToolResult: (payload) =>
          events.push(
            `tool_result:${payload.tool}:${payload.hits}:${payload.ok}`,
          ),
        onDone: () => events.push("done"),
        onError: () => {
          throw new Error("不应出现 error 事件");
        },
      },
      undefined,
    );

    expect(events).toEqual([
      "status",
      "tool_call:search_transcript:MVCC",
      "tool_result:search_transcript:3:true",
      "token",
      "tool_call:search_transcript:undo",
      "tool_result:search_transcript:0:false",
      "done",
    ]);
    expect(tokens).toEqual(["命中"]);
  });

  it("done 载荷 research_proposals 防御性收窄：合法条目透传，畸形条目静默跳过", async () => {
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        () => {
          const { stream } = sseBody([
            'event: status\ndata: {"phase":"generating"}\n\n',
            'event: done\ndata: {"message_id":"m1","content":"结论","memory_used":[],"research_proposals":[{"proposal_id":"p1","url":"https://a.example.com/1","title":"来源 A"},{"proposal_id":42},{"proposal_id":"p2","url":"https://b.example.com","title":"来源 B","extra":true},"oops"]}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    let donePayload:
      | Parameters<Parameters<typeof chatApi.streamMessage>[2]["onDone"]>[0]
      | null = null;
    await chatApi.streamMessage(
      SESSION_ID,
      "研究问题",
      {
        onStatus: () => undefined,
        onToken: () => undefined,
        onToolCall: () => undefined,
        onToolResult: () => undefined,
        onDone: (payload) => {
          donePayload = payload;
        },
        onError: () => {
          throw new Error("不应出现 error 事件");
        },
      },
      undefined,
    );

    expect(donePayload).toEqual({
      messageId: "m1",
      content: "结论",
      memoryUsed: [],
      researchProposals: [
        { proposalId: "p1", url: "https://a.example.com/1", title: "来源 A" },
        { proposalId: "p2", url: "https://b.example.com", title: "来源 B" },
      ],
    });
  });

  it("web_search 标志进请求体：显式 true 与缺省 false", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        async ({ request }) => {
          bodies.push(await request.json());
          const { stream } = sseBody([
            'event: done\ndata: {"message_id":"m1","content":"好"}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    const noop = () => undefined;
    await chatApi.streamMessage(
      SESSION_ID,
      "带标志",
      {
        onStatus: noop,
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: noop,
        onError: noop,
      },
      undefined,
      true,
    );
    await chatApi.streamMessage(
      SESSION_ID,
      "默认",
      {
        onStatus: noop,
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: noop,
        onError: noop,
      },
      undefined,
    );

    expect(bodies).toEqual([
      { content: "带标志", web_search: true },
      { content: "默认", web_search: false },
    ]);
  });

  it("page 快照进请求体：传入才携带，缺省不出现该键", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
        async ({ request }) => {
          bodies.push(await request.json());
          const { stream } = sseBody([
            'event: done\ndata: {"message_id":"m1","content":"好"}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );

    const noop = () => undefined;
    const handlers = {
      onStatus: noop,
      onToken: noop,
      onToolCall: noop,
      onToolResult: noop,
      onDone: noop,
      onError: noop,
    };
    await chatApi.streamMessage(
      SESSION_ID,
      "带页面",
      handlers,
      undefined,
      false,
      {
        page_type: "chat",
        captured_at: "2026-09-21T08:00:00.000Z",
      },
    );
    await chatApi.streamMessage(SESSION_ID, "无页面", handlers, undefined);

    expect(bodies).toEqual([
      {
        content: "带页面",
        web_search: false,
        page: { page_type: "chat", captured_at: "2026-09-21T08:00:00.000Z" },
      },
      { content: "无页面", web_search: false },
    ]);
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
        onToolCall: () => undefined,
        onToolResult: () => undefined,
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
          onToolCall: () => undefined,
          onToolResult: () => undefined,
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
        onToolCall: () => undefined,
        onToolResult: () => undefined,
        onDone: () => undefined,
        onError: () => undefined,
      },
      controller.signal,
    );
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    close();
  });

  // SSE 错误载荷经同一翻译入口（spec 缝隙 4）：node 环境无 window 不能导入 @/i18n，
  // 用真实资源直接初始化同一 i18next 单例验证生产码表。
  describe("SSE 错误载荷按码翻译", () => {
    beforeAll(async () => {
      await i18next.init({
        lng: "zh",
        fallbackLng: "zh",
        resources: { zh: { translation: zh }, en: { translation: en } },
        interpolation: { escapeValue: false },
      });
    });

    afterEach(async () => {
      if (i18next.language !== "zh") await i18next.changeLanguage("zh");
    });

    async function collectErrors(
      errorEvent: string,
    ): Promise<{ code: string; detail: string }[]> {
      const { stream } = sseBody([errorEvent]);
      server.use(
        http.post(
          `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/messages`,
          () =>
            new HttpResponse(stream, {
              headers: { "Content-Type": "text/event-stream" },
            }),
        ),
      );
      const errors: { code: string; detail: string }[] = [];
      await chatApi.streamMessage(
        SESSION_ID,
        "提问",
        {
          onStatus: () => undefined,
          onToken: () => undefined,
          onToolCall: () => undefined,
          onToolResult: () => undefined,
          onDone: () => undefined,
          onError: (payload) => errors.push(payload),
        },
        undefined,
      );
      return errors;
    }

    it("英文界面下按码取英文译文", async () => {
      await i18next.changeLanguage("en");
      const errors = await collectErrors(
        'event: error\ndata: {"code":"CHAT_STREAM_FAILED","detail":"回答生成失败，请稍后重试"}\n\n',
      );
      expect(errors).toEqual([
        {
          code: "CHAT_STREAM_FAILED",
          detail: "The answer failed to generate. Please try again later.",
        },
      ]);
    });

    it("中文界面按码取中文文案；未命中的码回显原文", async () => {
      expect(
        await collectErrors(
          'event: error\ndata: {"code":"EMPTY_REPLY","detail":"回答为空，请重试"}\n\n',
        ),
      ).toEqual([{ code: "EMPTY_REPLY", detail: "回答为空，请重试" }]);
      expect(
        await collectErrors(
          'event: error\ndata: {"code":"FUTURE_SSE_CODE","detail":"未来错误原文"}\n\n',
        ),
      ).toEqual([{ code: "FUTURE_SSE_CODE", detail: "未来错误原文" }]);
    });
  });
});
