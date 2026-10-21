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
const TURN_ID = "tttttttt-tttt-4ttt-8ttt-tttttttttttt";

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

function turnEventsHandler(events: string[], keepOpen = false) {
  const { stream, close } = sseBody(events, keepOpen);
  return {
    close,
    handler: http.get(
      `${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/events`,
      () =>
        new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        }),
    ),
  };
}

const noop = () => undefined;

describe("chatApi.turnEvents", () => {
  it("保留委派进度与等待快照的身份供显式决定使用", async () => {
    const entry = {
      kind: "delegation",
      id: "child-1",
      execution_id: "child-1",
      agent_id: "knowledge",
      execution_attempt: 2,
      status: "INTERRUPTED",
      error_code: null,
    };
    const reason = {
      kind: "DELEGATION_UNCERTAIN",
      snapshot_id: "snapshot-1",
      detail: "等待选择",
      delegations: [
        {
          execution_id: "child-1",
          execution_attempt: 2,
          request_ids: ["request-1"],
        },
      ],
    };
    const process = {
      id: TURN_ID,
      session_id: SESSION_ID,
      user_message_id: "m1",
      assistant_message_id: null,
      status: "RUNNING",
      started_at: "2026-10-21T10:00:00Z",
      updated_at: "2026-10-21T10:00:01Z",
      ended_at: null,
      elapsed_ms: 1000,
      history_saved: true,
      entries: [entry],
    };
    const { handler } = turnEventsHandler([
      `event: status\ndata: ${JSON.stringify({ phase: "waiting_user", reason, process })}\n\n`,
    ]);
    server.use(handler);
    const onStatus = vi.fn();
    await chatApi.turnEvents(
      TURN_ID,
      0,
      {
        onStatus,
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: noop,
        onError: noop,
      },
      undefined,
    );
    expect(onStatus).toHaveBeenCalledWith(
      expect.objectContaining({ reason, process }),
    );
  });
  it("按到达顺序逐 token 回调，done 携带完整内容与消息 id", async () => {
    const { handler } = turnEventsHandler([
      'event: status\ndata: {"phase":"generating"}\n\n',
      'event: token\ndata: {"text":"操"}\n\n',
      'event: token\ndata: {"text":"作"}\n\n',
      'event: token\ndata: {"text":"系统"}\n\n',
      'event: done\ndata: {"message_id":"m1","content":"操作系统"}\n\n',
    ]);
    server.use(handler);

    const tokens: string[] = [];
    let statusCount = 0;
    let donePayload: { messageId: string; content: string } | null = null;
    await chatApi.turnEvents(
      TURN_ID,
      0,
      {
        onStatus: () => {
          statusCount += 1;
        },
        onToken: (text) => tokens.push(text),
        onToolCall: noop,
        onToolResult: noop,
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
    const { handler } = turnEventsHandler([
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
    server.use(handler);

    const events: string[] = [];
    const tokens: string[] = [];
    await chatApi.turnEvents(
      TURN_ID,
      0,
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
    const { handler } = turnEventsHandler([
      'event: status\ndata: {"phase":"generating"}\n\n',
      'event: done\ndata: {"message_id":"m1","content":"结论","memory_used":[],"research_proposals":[{"proposal_id":"p1","url":"https://a.example.com/1","title":"来源 A"},{"proposal_id":42},{"proposal_id":"p2","url":"https://b.example.com","title":"来源 B","extra":true},"oops"]}\n\n',
    ]);
    server.use(handler);

    let donePayload: { messageId: string; content: string } | null = null;
    await chatApi.turnEvents(
      TURN_ID,
      0,
      {
        onStatus: noop,
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: (payload) => {
          donePayload = payload;
        },
        onError: () => {
          throw new Error("不应出现 error 事件");
        },
      },
      undefined,
    );

    expect(donePayload).toMatchObject({
      messageId: "m1",
      content: "结论",
      memoryUsed: [],
      researchProposals: [
        { proposalId: "p1", url: "https://a.example.com/1", title: "来源 A" },
        { proposalId: "p2", url: "https://b.example.com", title: "来源 B" },
      ],
    });
  });

  it("游标进查询串：after_seq 透传", async () => {
    const queries: string[] = [];
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/events`,
        ({ request }) => {
          queries.push(new URL(request.url).search);
          const { stream } = sseBody([
            'event: done\ndata: {"message_id":"m1","content":"好"}\n\n',
          ]);
          return new HttpResponse(stream, {
            headers: { "Content-Type": "text/event-stream" },
          });
        },
      ),
    );
    await chatApi.turnEvents(
      TURN_ID,
      7,
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
    expect(queries).toEqual(["?after_seq=7"]);
  });

  it("error 事件回调可读错误码；非 2xx 由 apiRequest 转为 ApiError", async () => {
    const errors: { code: string; detail: string }[] = [];
    const { handler } = turnEventsHandler([
      'event: error\ndata: {"code":"CHAT_STREAM_FAILED","detail":"回答生成失败，请稍后重试"}\n\n',
    ]);
    server.use(handler);
    await chatApi.turnEvents(
      TURN_ID,
      0,
      {
        onStatus: noop,
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: noop,
        onError: (payload) => errors.push(payload),
      },
      undefined,
    );
    expect(errors).toEqual([
      { code: "CHAT_STREAM_FAILED", detail: "回答生成失败，请稍后重试" },
    ]);

    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/events`, () =>
        HttpResponse.json({ detail: "轮次不存在" }, { status: 404 }),
      ),
    );
    await expect(
      chatApi.turnEvents(
        TURN_ID,
        0,
        {
          onStatus: noop,
          onToken: noop,
          onToolCall: noop,
          onToolResult: noop,
          onDone: noop,
          onError: noop,
        },
        undefined,
      ),
    ).rejects.toMatchObject({ status: 404 });
  });

  it("断开信号只取消订阅并转抛 AbortError（不作业务停止）", async () => {
    const { handler, close } = turnEventsHandler(
      ['event: status\ndata: {"phase":"generating"}\n\n'],
      true,
    );
    server.use(handler);

    const controller = new AbortController();
    const pending = chatApi.turnEvents(
      TURN_ID,
      0,
      {
        onStatus: () => controller.abort(),
        onToken: noop,
        onToolCall: noop,
        onToolResult: noop,
        onDone: noop,
        onError: noop,
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
      const { handler } = turnEventsHandler([errorEvent]);
      server.use(handler);
      const errors: { code: string; detail: string }[] = [];
      await chatApi.turnEvents(
        TURN_ID,
        0,
        {
          onStatus: noop,
          onToken: noop,
          onToolCall: noop,
          onToolResult: noop,
          onDone: noop,
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

describe("chatApi.submitTurn", () => {
  it("请求体携带 content/web_search/request_id 与可选 page/auth_mode", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/turns`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(
            {
              id: TURN_ID,
              session_id: SESSION_ID,
              user_message_id: "m0",
              status: "QUEUED",
              cancel_requested: false,
              attempt: 0,
              output_revision: 1,
              last_seq: 0,
              created_at: "2026-10-06T00:00:00.000000Z",
              updated_at: "2026-10-06T00:00:00.000000Z",
              output_text: "",
            },
            { status: 202 },
          );
        },
      ),
    );

    await chatApi.submitTurn(SESSION_ID, {
      content: "带全部字段",
      webSearch: true,
      requestId: "req-body-0001",
      page: {
        page_type: "chat",
        captured_at: "2026-10-06T08:00:00.000Z",
      },
      authMode: "AUTO_APPROVE",
    });
    await chatApi.submitTurn(SESSION_ID, {
      content: "最小字段",
      webSearch: false,
      requestId: "req-body-0002",
    });

    expect(bodies).toEqual([
      {
        content: "带全部字段",
        web_search: true,
        request_id: "req-body-0001",
        page: { page_type: "chat", captured_at: "2026-10-06T08:00:00.000Z" },
        auth_mode: "AUTO_APPROVE",
      },
      { content: "最小字段", web_search: false, request_id: "req-body-0002" },
    ]);
  });

  it("会话在途冲突（409）转为 ApiError", async () => {
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/turns`,
        () =>
          HttpResponse.json(
            {
              detail:
                "CHAT_TURN_IN_PROGRESS：该对话正在生成回答，请稍候或先停止",
              code: "CHAT_TURN_IN_PROGRESS",
            },
            { status: 409 },
          ),
      ),
    );
    await expect(
      chatApi.submitTurn(SESSION_ID, {
        content: "冲突提问",
        webSearch: false,
        requestId: "req-conflict-1",
      }),
    ).rejects.toMatchObject({ status: 409 });
  });
});

describe("chatApi.activeTurn", () => {
  it("返回唯一非终态轮次；空列表返回 null", async () => {
    let expectActive = true;
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${SESSION_ID}/turns`,
        () =>
          HttpResponse.json(
            expectActive
              ? {
                  turns: [
                    {
                      id: TURN_ID,
                      session_id: SESSION_ID,
                      user_message_id: "m0",
                      status: "RUNNING",
                      cancel_requested: false,
                      attempt: 1,
                      output_revision: 1,
                      last_seq: 3,
                      created_at: "2026-10-06T00:00:00.000000Z",
                      updated_at: "2026-10-06T00:00:01.000000Z",
                      output_text: "部分输出",
                    },
                  ],
                  next_before: null,
                }
              : { turns: [], next_before: null },
          ),
      ),
    );
    const active = await chatApi.activeTurn(SESSION_ID);
    expect(active?.id).toBe(TURN_ID);
    expect(active?.status).toBe("RUNNING");
    expectActive = false;
    expect(await chatApi.activeTurn(SESSION_ID)).toBeNull();
  });
});
