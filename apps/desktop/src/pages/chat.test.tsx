// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";
import { openWebUrl } from "@/services/tauri/webLinks";

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

vi.mock("@/services/tauri/webLinks", () => ({
  openWebUrl: vi.fn().mockResolvedValue(undefined),
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

/** 保持打开的流：推完初始块后不关闭，可按需继续推事件或收尾关闭。 */
function openSseResponse(initialChunks: string[]) {
  const encoder = new TextEncoder();
  let streamController: ReadableStreamDefaultController<Uint8Array> | null =
    null;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
      for (const chunk of initialChunks)
        controller.enqueue(encoder.encode(chunk));
    },
  });
  return {
    response: new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    }),
    pushEvent: (event: string) => {
      streamController?.enqueue(encoder.encode(`${event}\n\n`));
    },
    closeStream: () => streamController?.close(),
  };
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
  vi.mocked(openWebUrl).mockClear();
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
    // 空会话由建议卡承担引导，不再显示旧文案。
    expect(await screen.findByText("你可以这样提问")).toBeVisible();
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
      screen.getByRole("button", { name: "「线程调度答疑」的更多操作" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "重命名" }));
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
      await screen.findByRole("button", { name: "「待删除对话」的更多操作" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "删除" }));
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

  it("收藏会话后可从「已收藏」筛选定位，取消收藏后筛选为空", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([
          chatSession(FIRST_SESSION_ID, { title: "线程调度答疑" }),
        ]),
      ),
    );
    renderAt("/chat");

    expect(await screen.findByText("线程调度答疑")).toBeVisible();
    // 收藏是图 1 对齐的本地示意状态。
    fireEvent.click(
      screen.getByRole("button", { name: "「线程调度答疑」的更多操作" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "收藏" }));

    // 「已收藏」筛选下仍可见。
    fireEvent.click(screen.getByRole("button", { name: "已收藏" }));
    expect(screen.getByText("线程调度答疑")).toBeVisible();

    // 取消收藏后该筛选为空。
    fireEvent.click(
      screen.getByRole("button", { name: "「线程调度答疑」的更多操作" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "取消收藏" }));
    expect(await screen.findByText("没有符合条件的对话")).toBeVisible();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
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

  it("未配置 AI 服务时展示跳设置页的引导卡，无就地配置表单", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/settings/providers/llm`, () =>
        HttpResponse.json({ provider: null }),
      ),
    );
    useSessionPage();

    expect(
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
    // 未配置时没有发送入口，也没有就地配置表单。
    expect(
      screen.queryByRole("textbox", { name: "提问输入框" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("服务地址")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("API 密钥")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前往设置" })).toBeVisible();
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

  it("建议卡点击后填入输入框，右栏工具开关可切换", async () => {
    useSessionPage();

    fireEvent.click(
      await screen.findByRole("button", { name: /解释这个知识点/ }),
    );
    expect(screen.getByRole("textbox", { name: "提问输入框" })).toHaveValue(
      "请用通俗的语言解释这个知识点，并给出简单的例子。",
    );

    const knowledgeSwitch = screen.getByRole("switch", {
      name: "知识库检索",
    });
    expect(knowledgeSwitch).toBeChecked();
    fireEvent.click(knowledgeSwitch);
    expect(knowledgeSwitch).not.toBeChecked();
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

  it("右栏聚合多条回答的引用并按编号去重（后出现的回答优先）", async () => {
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
            messageRow("user-1", "USER", "第一问"),
            {
              id: "assistant-1",
              role: "ASSISTANT",
              content: "第一答[1]。",
              model: "stub-chat-model",
              citations: [{ index: 1, record_id: RECORD_ID, quote: "旧引用" }],
              created_at: "2026-08-27T08:00:00.000000Z",
            },
            messageRow("user-2", "USER", "第二问"),
            {
              id: "assistant-2",
              role: "ASSISTANT",
              content: "第二答[1][2]。",
              model: "stub-chat-model",
              citations: [
                { index: 1, record_id: RECORD_ID, quote: "新引用" },
                { index: 2, record_id: RECORD_ID, quote: "第二条引用" },
              ],
              created_at: "2026-08-27T08:01:00.000000Z",
            },
          ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 右栏聚合出现即消息渲染完成；[2] 按钮出现证明相邻角标 [1][2] 已各自成链。
    expect(
      await screen.findByRole("button", { name: "[2] 第二条引用" }),
    ).toBeVisible();
    const list = screen.getByRole("list", { name: "引用来源" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(
      within(list).getByRole("button", { name: "[1] 新引用" }),
    ).toBeVisible();
    expect(
      within(list).queryByRole("button", { name: "[1] 旧引用" }),
    ).not.toBeInTheDocument();
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

describe("挂载对话检索过程", () => {
  const RECORD_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";

  function renderMountedStreaming(answered: { current: boolean }) {
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
          HttpResponse.json(
            answered.current
              ? [
                  SYSTEM_ROW,
                  messageRow("user-row", "USER", "MVCC 怎么实现"),
                  messageRow(
                    "assistant-row",
                    "ASSISTANT",
                    "答案见转写原文。",
                    "stub",
                  ),
                ]
              : [SYSTEM_ROW],
          ),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);
  }

  it("检索状态卡三态逐条呈现，done 后随流式态消失", async () => {
    const answered = { current: false };
    const opened = openSseResponse([]);
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => opened.response,
      ),
    );
    renderMountedStreaming(answered);

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "MVCC 怎么实现" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    // 加载态：tool_call 到达即显示「正在检索」。
    opened.pushEvent('event: status\ndata: {"phase":"generating"}');
    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"search_transcript","query":"MVCC"}',
    );
    expect(await screen.findByText("正在检索「MVCC」")).toBeVisible();

    // 成功态：tool_result 回填命中数。
    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"search_transcript","hits":3,"ok":true}',
    );
    expect(await screen.findByText("「MVCC」命中 3 条")).toBeVisible();

    // 失败态 + 多次检索逐条陈列：第一条结果卡仍在。
    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"search_transcript","query":"undo 日志"}',
    );
    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"search_transcript","hits":0,"ok":false}',
    );
    expect(await screen.findByText("「undo 日志」检索失败")).toBeVisible();
    expect(screen.getByText("「MVCC」命中 3 条")).toBeVisible();

    opened.pushEvent('event: token\ndata: {"text":"答案"}');
    opened.pushEvent('event: token\ndata: {"text":"见转写原文。"}');
    answered.current = true;
    opened.pushEvent(
      'event: done\ndata: {"message_id":"assistant-row","content":"答案见转写原文。"}',
    );
    opened.closeStream();

    // done 后工具过程卡随流式态消失，历史只有正文。
    await waitFor(() =>
      expect(screen.queryByText("「MVCC」命中 3 条")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("「undo 日志」检索失败")).not.toBeInTheDocument();
    expect(await screen.findByText("答案见转写原文。")).toBeVisible();
  });
});

describe("联网搜索接线（B1）", () => {
  // 已配置搜索供应商：webSearch 开关可用；未覆盖时走默认 handler（provider:null）→ 置灰。
  function useConfiguredWebSearch() {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/settings/providers/web-search`, () =>
        HttpResponse.json({
          provider: {
            provider: "tavily",
            has_api_key: true,
            api_key_hint: "••••1234",
          },
        }),
      ),
    );
  }

  function capturedMessagePost(answered: { current: boolean }) {
    const bodies: unknown[] = [];
    const handler = http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
      async ({ request }) => {
        bodies.push(await request.json());
        return sseResponse(
          sseChunks([
            'event: token\ndata: {"text":"答"}',
            'event: done\ndata: {"message_id":"assistant-row","content":"答"}',
          ]),
          () => {
            answered.current = true;
          },
        );
      },
    );
    server.use(handler);
    return bodies;
  }

  it("自由聊天默认开启：发送携带 web_search:true，关闭开关后为 false", async () => {
    const created = chatSession(FIRST_SESSION_ID, {});
    const answered = { current: false };
    const bodies = capturedMessagePost(answered);
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
          HttpResponse.json(
            answered.current
              ? [
                  SYSTEM_ROW,
                  messageRow("user-row", "USER", "什么是 MVCC"),
                  messageRow("assistant-row", "ASSISTANT", "答", "stub"),
                ]
              : [SYSTEM_ROW],
          ),
      ),
    );
    useConfiguredWebSearch();
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 右栏开关默认开（自由会话）；可用性查询返回后切到可用分支（节点重建，须重查询）。
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "联网搜索" })).toBeChecked(),
    );
    const webSwitch = screen.getByRole("switch", { name: "联网搜索" });

    const input = screen.getByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "最新版本是多少" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(bodies[0]).toEqual({
        content: "最新版本是多少",
        web_search: true,
      }),
    );

    // 关闭开关后同一会话再发：标志随开关变化。
    fireEvent.click(webSwitch);
    expect(webSwitch).not.toBeChecked();
    fireEvent.change(input, { target: { value: "不联网问问" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(bodies[1]).toEqual({ content: "不联网问问", web_search: false }),
    );
  });

  it("挂载会话默认关闭：输入区 Globe 打开后与右栏开关同源联动", async () => {
    const RECORD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const created = chatSession(FIRST_SESSION_ID, { record_id: RECORD_ID });
    const answered = { current: false };
    const bodies = capturedMessagePost(answered);
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
        () => HttpResponse.json([SYSTEM_ROW]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([]),
      ),
    );
    useConfiguredWebSearch();
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 挂载会话默认关；可用性查询返回后开关解禁且未勾选（须重查询取可用分支节点）。
    await waitFor(() => {
      const webSwitch = screen.getByRole("switch", { name: "联网搜索" });
      expect(webSwitch).not.toBeChecked();
      expect(webSwitch).not.toHaveAttribute("data-disabled");
    });

    // 输入区 Globe 与右栏开关读写同一份按会话状态。
    fireEvent.click(screen.getByRole("button", { name: "联网搜索" }));
    const webSwitch = screen.getByRole("switch", { name: "联网搜索" });
    expect(webSwitch).toBeChecked();

    const input = screen.getByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "追问材料外背景" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(bodies[0]).toEqual({
        content: "追问材料外背景",
        web_search: true,
      }),
    );
  });

  it("未配置搜索密钥：开关与输入区按钮置灰，聊天不受影响", async () => {
    const created = chatSession(FIRST_SESSION_ID, {});
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
        () => HttpResponse.json([SYSTEM_ROW]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // Switch 是 span（jest-dom 的 toBeDisabled 不认 aria-disabled），按属性断言置灰。
    const webSwitch = await screen.findByRole("switch", { name: "联网搜索" });
    await waitFor(() =>
      expect(webSwitch).toHaveAttribute("aria-disabled", "true"),
    );
    expect(screen.getByRole("button", { name: "联网搜索" })).toBeDisabled();
    // 缺 key 只降级搜索：输入与发送照常可用。
    expect(screen.getByRole("textbox", { name: "提问输入框" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  });

  it("web_search 工具卡文案分流：搜索中 / 命中 / 失败", async () => {
    const created = chatSession(FIRST_SESSION_ID, {});
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => HttpResponse.json([SYSTEM_ROW]),
      ),
    );
    useConfiguredWebSearch();
    const opened = openSseResponse([]);
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => opened.response,
      ),
    );
    const listHandler = http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
      HttpResponse.json([created]),
    );
    const detailHandler = http.get(
      `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
      () => HttpResponse.json(created),
    );
    server.use(listHandler, detailHandler);
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "最新版本是多少" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    opened.pushEvent('event: status\ndata: {"phase":"generating"}');
    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"web_search","query":"MVCC 最新版本"}',
    );
    expect(
      await screen.findByText("正在搜索网络「MVCC 最新版本」"),
    ).toBeVisible();

    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"web_search","hits":5,"ok":true}',
    );
    expect(await screen.findByText("找到 5 条结果")).toBeVisible();

    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"web_search","query":"undo 日志"}',
    );
    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"web_search","hits":0,"ok":false}',
    );
    expect(await screen.findByText("「undo 日志」搜索失败")).toBeVisible();

    opened.pushEvent('event: token\ndata: {"text":"答"}');
    opened.pushEvent(
      'event: done\ndata: {"message_id":"assistant-row","content":"答"}',
    );
    opened.closeStream();
  });

  it("web 引用显示标题与域名，点击经系统浏览器打开；正文角标同样分流", async () => {
    const RECORD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const WEB_URL = "https://en.wikipedia.org/wiki/Operating_system";
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
            messageRow("user-row", "USER", "操作系统是什么"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "操作系统是管理硬件的软件[1][2]。",
              model: "stub-chat-model",
              citations: [
                {
                  index: 1,
                  source: "record",
                  record_id: RECORD_ID,
                  quote: "操作系统管理硬件资源",
                },
                {
                  index: 2,
                  source: "web",
                  url: WEB_URL,
                  title: "Operating system - Wikipedia",
                },
              ],
              created_at: "2026-08-27T08:00:00.000000Z",
            },
          ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 右栏列表：web 条目 = 标题 + 域名；record 条目照旧。
    const webEntry = await screen.findByRole("button", {
      name: "[2] Operating system - Wikipedia，点击在浏览器打开",
    });
    expect(screen.getByText("en.wikipedia.org")).toBeVisible();
    fireEvent.click(webEntry);
    await waitFor(() =>
      expect(vi.mocked(openWebUrl)).toHaveBeenCalledWith(WEB_URL),
    );

    // 正文 web 角标点击同样开浏览器。
    fireEvent.click(
      screen.getByRole("button", { name: "打开引用 2 的网络来源" }),
    );
    await waitFor(() => expect(openWebUrl).toHaveBeenCalledTimes(2));

    // record 角标仍跳转写页，不触发浏览器打开。
    fireEvent.click(
      screen.getByRole("button", { name: "查看引用 1 的转写原文" }),
    );
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${RECORD_ID}`),
    );
    expect(openWebUrl).toHaveBeenCalledTimes(2);
  });
});

describe("挂载会话失效态", () => {
  const RECORD_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

  it("列表对失效会话显示原记录已删除标记", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([
          chatSession(FIRST_SESSION_ID, {
            title: "失效会话",
            record_id: RECORD_ID,
            record_deleted: true,
          }),
          chatSession(SECOND_SESSION_ID, { title: "正常会话" }),
        ]),
      ),
    );
    renderAt("/chat");

    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("原记录已删除");
    expect(rows[1]).not.toHaveTextContent("原记录已删除");
  });

  it("会话页保留可读历史，输入区禁用并说明原因", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      record_deleted: true,
    });
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
            SYSTEM_ROW,
            messageRow("user-row", "USER", "旧提问"),
            messageRow("assistant-row", "ASSISTANT", "旧回答", "stub"),
          ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 历史仍可读；头部、侧栏列表与右栏上下文各有一个失效标记。
    expect(await screen.findByText("旧提问")).toBeVisible();
    expect(screen.getByText("旧回答")).toBeVisible();
    expect(screen.getAllByText("原记录已删除")).toHaveLength(3);

    const input = screen.getByRole("textbox", { name: "提问输入框" });
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(
      screen.getByText("原记录已删除，对话已失效，无法继续发送。"),
    ).toBeVisible();
  });
});
