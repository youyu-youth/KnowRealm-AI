// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/services/tauri/recording", () => ({
  setRecordingKeepAwake: vi.fn().mockResolvedValue(undefined),
  hideWindowTemporarily: vi.fn().mockResolvedValue(undefined),
}));

vi.stubGlobal("scrollTo", vi.fn());
window.Element.prototype.scrollIntoView = vi.fn();

const FIRST_SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SECOND_SESSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

type ChatSessionOut = components["schemas"]["ChatSessionOut"];

function chatSession(
  id: string,
  overrides: Partial<ChatSessionOut>,
): ChatSessionOut {
  return {
    id,
    mode: "ASK",
    title: null,
    record_id: null,
    course_id: null,
    record_deleted: false,
    created_at: "2026-08-27T08:00:00.000000Z",
    updated_at: "2026-08-27T08:00:00.000000Z",
    ...overrides,
  };
}

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

function messageRow(
  id: string,
  role: string,
  content: string,
  model: string | null = null,
) {
  return {
    id,
    role,
    content,
    model,
    created_at: "2026-08-27T08:00:00.000000Z",
  };
}

const SYSTEM_ROW = {
  id: "system-row",
  role: "SYSTEM",
  content: "你是 KnowRealm 学习助手。",
  model: null,
  created_at: "2026-08-27T08:00:00.000000Z",
};

function sseChunks(events: string[]): string[] {
  return events.map((event) => `${event}\n\n`);
}

function sseResponse(chunks: string[], onClose?: () => void) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
      onClose?.();
    },
  });
  return new HttpResponse(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}

/** 保持打开的流：推完初始块后不关闭，返回关闭器供“停止”场景收尾。 */
function openSseResponse(initialChunks: string[]) {
  const encoder = new TextEncoder();
  let closeStream = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of initialChunks)
        controller.enqueue(encoder.encode(chunk));
      closeStream = () => controller.close();
    },
  });
  return {
    response: new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    }),
    closeStream: () => closeStream(),
  };
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("AI 对话", () => {
  it("空态如实展示引导卡，不出现对话列表", async () => {
    renderAt("/chat");

    expect(
      await screen.findByRole("heading", { name: "开始第一场对话" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "开始对话" })).toBeEnabled();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("新建自由对话后立即进入会话页，显示提问输入区", async () => {
    const created = chatSession(FIRST_SESSION_ID, {});
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([]),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json(created, { status: 201 }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([created]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(created),
      ),
    );

    renderAt("/chat");
    fireEvent.click(await screen.findByRole("button", { name: "新建对话" }));
    fireEvent.click(await screen.findByRole("button", { name: "创建对话" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    expect(
      await screen.findByRole("heading", { name: "新对话" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("textbox", { name: "提问输入框" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
    // 空会话只有 SYSTEM 快照（不渲染），给出引导文案。
    expect(await screen.findByText("向 AI 提出第一个问题吧")).toBeVisible();
  });

  it("新建时可挂载收件箱记录，无转写记录置灰并说明原因", async () => {
    const recordId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    const created = chatSession(FIRST_SESSION_ID, { record_id: recordId });
    let body: unknown;
    let attempts = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([
          {
            id: recordId,
            title: "公式速记",
            course_id: null,
            has_transcript: true,
          },
          {
            id: "pending",
            title: "导入处理中",
            course_id: null,
            has_transcript: false,
          },
        ]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions`,
        async ({ request }) => {
          body = await request.json();
          if (++attempts === 1)
            return HttpResponse.json(
              { detail: "暂时无法挂载，请重试" },
              { status: 409 },
            );
          return HttpResponse.json(created, { status: 201 });
        },
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(created),
      ),
    );
    renderAt("/chat");
    fireEvent.click(await screen.findByRole("button", { name: "新建对话" }));
    fireEvent.click(
      await screen.findByRole("combobox", { name: "挂载学习记录（可选）" }),
    );
    const unavailable = await screen.findByRole("option", {
      name: /导入处理中.*转写尚未生成/,
    });
    expect(unavailable).toHaveAttribute("aria-disabled", "true");
    const option = screen.getByRole("option", { name: /公式速记.*收件箱/ });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveTextContent("公式速记"),
    );
    expect(
      screen.getByText("创建后不能更换或取消挂载。未挂载时使用自由聊天。"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "创建对话" }));
    expect(await screen.findByText("暂时无法挂载，请重试")).toBeVisible();
    expect(screen.getByRole("combobox")).toHaveTextContent("公式速记");
    fireEvent.click(screen.getByRole("button", { name: "创建对话" }));
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    expect(body).toEqual({ mode: "ASK", record_id: recordId });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("列表按最近更新排序，重命名即时生效且不改变排序", async () => {
    let renamed = false;
    const first = chatSession(FIRST_SESSION_ID, { title: "线程调度答疑" });
    const second = chatSession(SECOND_SESSION_ID, { title: "文件系统速记" });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json(
          renamed
            ? [second, chatSession(FIRST_SESSION_ID, { title: "操作系统答疑" })]
            : [second, first],
        ),
      ),
      http.patch(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => {
          renamed = true;
          return HttpResponse.json(
            chatSession(FIRST_SESSION_ID, { title: "操作系统答疑" }),
          );
        },
      ),
    );

    renderAt("/chat");

    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("文件系统速记");
    expect(rows[1]).toHaveTextContent("线程调度答疑");

    fireEvent.click(
      screen.getByRole("button", { name: "重命名 线程调度答疑" }),
    );
    expect(
      await screen.findByRole("heading", { name: "重命名对话" }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("对话标题"), {
      target: { value: "操作系统答疑" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("操作系统答疑")).toBeVisible();
    const updatedRows = screen.getAllByRole("listitem");
    expect(updatedRows[0]).toHaveTextContent("文件系统速记");
    expect(updatedRows[1]).toHaveTextContent("操作系统答疑");
    expect(screen.queryByText("线程调度答疑")).not.toBeInTheDocument();
  });

  it("删除前弹窗明示不可恢复，确认后对话不再出现", async () => {
    let deleted = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json(
          deleted
            ? []
            : [chatSession(FIRST_SESSION_ID, { title: "待删除对话" })],
        ),
      ),
      http.delete(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => {
          deleted = true;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    renderAt("/chat");

    fireEvent.click(
      await screen.findByRole("button", { name: "删除 待删除对话" }),
    );
    expect(
      await screen.findByRole("heading", { name: "删除对话" }),
    ).toBeVisible();
    expect(screen.getByText(/不可恢复/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() =>
      expect(screen.queryByText("待删除对话")).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByRole("heading", { name: "开始第一场对话" }),
    ).toBeVisible();
  });

  it("会话页对不存在的会话给出诚实状态与返回入口", async () => {
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () =>
          HttpResponse.json({ detail: "对话不存在或已删除" }, { status: 404 }),
      ),
    );

    renderAt(`/chat/${FIRST_SESSION_ID}`);

    expect(
      await screen.findByRole(
        "heading",
        { name: "对话不存在或已删除" },
        {
          timeout: 8_000,
        },
      ),
    ).toBeVisible();
    const back = screen.getByRole("link", { name: "返回对话列表" });
    expect(back).toHaveAttribute("href", "/chat");
  });
});

describe("自由聊天流式", () => {
  function useSessionPage() {
    const created = chatSession(FIRST_SESSION_ID, {});
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([created]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(created),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);
  }

  it("发送后流式逐字渲染，完成后历史重取展示双方消息", async () => {
    let answered = false;
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json(
            answered
              ? [
                  SYSTEM_ROW,
                  messageRow("user-row", "USER", "什么是 MVCC"),
                  messageRow(
                    "assistant-row",
                    "ASSISTANT",
                    "回答完成",
                    "stub-chat-model",
                  ),
                ]
              : [SYSTEM_ROW],
          ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          sseResponse(
            sseChunks([
              'event: status\ndata: {"phase":"generating"}',
              'event: token\ndata: {"text":"回答"}',
              'event: token\ndata: {"text":"完成"}',
              'event: done\ndata: {"message_id":"assistant-row","content":"回答完成"}',
            ]),
            () => {
              answered = true;
            },
          ),
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "什么是 MVCC" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    // token 逐字到达：先出现首片，再聚合为完整文本。
    expect(await screen.findByText("回答完成")).toBeVisible();
    expect(screen.getByText("什么是 MVCC")).toBeVisible();
    // done 后发送入口恢复，输入框清空。
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "发送" })).toBeEnabled(),
    );
    expect(input).toHaveValue("");
  });

  it("流式期间出现停止按钮且不可连发，停止后展示重新生成入口", async () => {
    const opened = openSseResponse(
      sseChunks(['event: status\ndata: {"phase":"generating"}']),
    );
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => opened.response,
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "长问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    // 受理后发送入口切换为停止。
    expect(await screen.findByRole("button", { name: "停止" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "发送" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));
    // 停止丢弃半截文本：流式气泡消失、发送恢复；末尾未回复提问露出重试入口。
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "发送" })).toBeEnabled(),
    );
    opened.closeStream();
  });

  it("在途冲突返回 409 并展示可读错误，之后仍可发送", async () => {
    let conflict = true;
    let answered = false;
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json(
            answered
              ? [
                  SYSTEM_ROW,
                  messageRow(
                    "assistant-row",
                    "ASSISTANT",
                    "好",
                    "stub-chat-model",
                  ),
                ]
              : [SYSTEM_ROW],
          ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => {
          if (conflict) {
            conflict = false;
            return HttpResponse.json(
              { detail: "CHAT_STREAM_IN_PROGRESS：该对话正在生成回答，请稍候" },
              { status: 409 },
            );
          }
          return sseResponse(
            sseChunks([
              'event: status\ndata: {"phase":"generating"}',
              'event: token\ndata: {"text":"好"}',
              'event: done\ndata: {"message_id":"assistant-row","content":"好"}',
            ]),
            () => {
              answered = true;
            },
          );
        },
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "第一条" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByText(/CHAT_STREAM_IN_PROGRESS：该对话正在生成回答/),
    ).toBeVisible();

    // 错误后可继续发问。
    fireEvent.change(screen.getByRole("textbox", { name: "提问输入框" }), {
      target: { value: "第二条" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("好")).toBeVisible();
  });

  it("未配置 AI 服务时展示空态配置卡，配置完成即可发送", async () => {
    let configured = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/settings/providers/llm`, () =>
        HttpResponse.json(
          configured
            ? {
                provider: {
                  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
                  model: "qwen-plus",
                  has_api_key: true,
                  api_key_hint: null,
                },
              }
            : { provider: null },
        ),
      ),
      http.put(`${TEST_SIDECAR_URL}/api/settings/providers/llm`, () => {
        configured = true;
        return HttpResponse.json({
          provider: {
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model: "qwen-plus",
            has_api_key: true,
            api_key_hint: "sk-…test",
          },
        });
      }),
    );
    useSessionPage();

    expect(
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
    // 未配置时没有发送入口。
    expect(
      screen.queryByRole("textbox", { name: "提问输入框" }),
    ).not.toBeInTheDocument();

    fireEvent.change(await screen.findByLabelText("服务地址"), {
      target: { value: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
    });
    fireEvent.change(await screen.findByLabelText("模型"), {
      target: { value: "qwen-plus" },
    });
    fireEvent.change(await screen.findByLabelText("API 密钥"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

    // 配置完成后查询失效重取，输入区出现。
    expect(
      await screen.findByRole("textbox", { name: "提问输入框" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "未配置 AI 服务" }),
    ).not.toBeInTheDocument();
  });

  it("历史末尾存在未回复提问时展示中断说明与重新生成按钮", async () => {
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json([
            SYSTEM_ROW,
            messageRow("user-row", "USER", "被中断的问题"),
          ]),
      ),
    );
    useSessionPage();

    expect(await screen.findByText("被中断的问题")).toBeVisible();
    expect(
      screen.getByText("上一条提问的回答被中断，没有保留半截内容。"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "重新生成回答" })).toBeEnabled();
  });
});

describe("挂载对话引用", () => {
  const RECORD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
  const QUOTE = "MVCC 依赖 undo 日志实现多版本读";

  function assistantRowWithCitations() {
    return {
      id: "assistant-row",
      role: "ASSISTANT",
      content: "MVCC 依赖 undo 日志[1]。",
      model: "stub-chat-model",
      citations: [{ index: 1, record_id: RECORD_ID, quote: QUOTE }],
      created_at: "2026-08-27T08:00:00.000000Z",
    };
  }

  function renderMountedSession() {
    const created = chatSession(FIRST_SESSION_ID, { record_id: RECORD_ID });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([created]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(created),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json([
            messageRow("user-row", "USER", "MVCC 怎么实现？"),
            assistantRowWithCitations(),
          ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);
  }

  it("回答展示角标与引用区，点击跳转记录转写页并携带定位摘录", async () => {
    renderMountedSession();

    // 角标渲染为子元素，正文按 textContent 整体断言。
    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "P" &&
          element.textContent === "MVCC 依赖 undo 日志[1]。",
      ),
    ).toBeVisible();
    expect(screen.getByRole("list", { name: "引用来源" })).toBeVisible();
    expect(screen.getByRole("button", { name: `[1] ${QUOTE}` })).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: "查看引用 1 的转写原文" }),
    );
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${RECORD_ID}`),
    );
    const search = new URLSearchParams(window.location.search);
    expect(search.get("tab")).toBe("transcript");
    expect(search.get("highlight")).toBe(QUOTE);
  });

  it("引用区条目同样可点击跳转", async () => {
    renderMountedSession();

    fireEvent.click(
      await screen.findByRole("button", { name: `[1] ${QUOTE}` }),
    );

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${RECORD_ID}`),
    );
  });

  it("角标无对应引用时保持纯文本，不出现可点击项", async () => {
    const created = chatSession(FIRST_SESSION_ID, { record_id: RECORD_ID });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([created]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(created),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json([
            messageRow("user-row", "USER", "再问"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "转写里没有对应角标来源[2]。",
              model: "stub-chat-model",
              citations: [],
              created_at: "2026-08-27T08:00:00.000000Z",
            },
          ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    expect(
      await screen.findByText("转写里没有对应角标来源[2]。"),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /查看引用/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "引用来源" })).toBeNull();
  });
});
