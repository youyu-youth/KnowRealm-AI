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
import {
  type DefaultBodyType,
  http,
  HttpResponse,
  type HttpHandler,
} from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { applyLanguage } from "@/i18n";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { useChatUiStore } from "@/features/chat/chatUiStore";
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
    agent_id: "general",
    mode: "ASK",
    scope: "FREE",
    title: null,
    record_id: null,
    course_id: null,
    record_deleted: false,
    course_deleted: false,
    library_item_deleted: false,
    created_at: "2026-08-27T08:00:00.000000Z",
    updated_at: "2026-08-27T08:00:00.000000Z",
    ...overrides,
  };
}

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

it("上下文排除、重置和选择旧轮共用持久版本，实际快照保持原设置", async () => {
  let version = 1;
  let segment = 1;
  let excluded = false;
  let included = true;
  const writes: components["schemas"]["ContextRuleChange"][] = [];
  const view = () => ({
    session_id: FIRST_SESSION_ID,
    version,
    segment,
    actual_turn_id: "original-turn",
    actual: [],
    actual_pins: [],
    pins: [],
    next_estimate: null,
    next_error_code: null,
    rules: {
      excluded_turn_ids: excluded ? ["original-turn"] : [],
      excluded_source_ids: [],
      included_turn_ids: included && segment > 1 ? ["original-turn"] : [],
    },
    actual_segment: 1,
    actual_rules: {
      excluded_turn_ids: [],
      excluded_source_ids: [],
      included_turn_ids: [],
    },
  });
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
      HttpResponse.json([chatSession(FIRST_SESSION_ID, {})]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`, () =>
      HttpResponse.json(chatSession(FIRST_SESSION_ID, {})),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/estimates`,
      () => HttpResponse.json(view()),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/history`, () =>
      HttpResponse.json({
        version,
        turns: [
          {
            turn_id: "original-turn",
            segment: 1,
            status: "COMPLETED",
            title: "明确选择的原轮",
            excluded,
            included: included && !excluded,
          },
        ],
        next_offset: null,
      }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/rules`,
      async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["ContextRuleChange"];
        writes.push(body);
        if (body.expected_version !== version)
          return HttpResponse.json(
            { code: "CONTEXT_VERSION_CONFLICT", detail: "设置已变化" },
            { status: 409 },
          );
        if (body.action === "EXCLUDE_TURN") excluded = true;
        if (body.action === "RESTORE_TURN") excluded = false;
        if (body.action === "RESET") {
          segment++;
          included = false;
        }
        if (body.action === "INCLUDE_HISTORY") included = true;
        version++;
        return HttpResponse.json({
          session_id: FIRST_SESSION_ID,
          version,
          segment,
          rules: view().rules,
        });
      },
    ),
  );
  renderAt(`/chat-context/${FIRST_SESSION_ID}?view=next`);
  await screen.findByRole(
    "heading",
    { name: "排除与历史承接" },
    { timeout: 5000 },
  );
  fireEvent.click(await screen.findByRole("button", { name: "排除此轮" }));
  await screen.findByRole("button", { name: "恢复此轮" });
  fireEvent.click(screen.getByRole("button", { name: "重置上下文" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText(/独立后台任务继续运行/)).toBeVisible();
  fireEvent.click(within(dialog).getByRole("button", { name: "开启新段" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  const include = await screen.findByRole("button", { name: "纳入此旧轮" });
  expect(include).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "恢复此轮" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "纳入此旧轮" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "纳入此旧轮" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "纳入此旧轮" }),
    ).not.toBeInTheDocument(),
  );
  expect(writes.map((body) => [body.action, body.expected_version])).toEqual([
    ["EXCLUDE_TURN", 1],
    ["RESET", 2],
    ["RESTORE_TURN", 3],
    ["INCLUDE_HISTORY", 4],
  ]);
  expect(writes[3].turn_ids).toEqual(["original-turn"]);
  fireEvent.click(screen.getByRole("tab", { name: "本轮实际输入" }));
  expect(
    await screen.findByText(
      "第 1 段 · 排除 0 轮 / 0 个来源 · 明确纳入 0 轮旧历史",
    ),
  ).toBeVisible();
});

it("资料原文排除提交明确来源版本，冲突不会显示成功", async () => {
  const writes: components["schemas"]["ContextRuleChange"][] = [];
  const view = {
    session_id: FIRST_SESSION_ID,
    version: 7,
    segment: 1,
    actual_turn_id: null,
    actual: [],
    actual_pins: [],
    pins: [],
    next_estimate: null,
    next_error_code: null,
  };
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
      HttpResponse.json([chatSession(FIRST_SESSION_ID, {})]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`, () =>
      HttpResponse.json(chatSession(FIRST_SESSION_ID, {})),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/context`, () =>
      HttpResponse.json(view),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/estimates`,
      () => HttpResponse.json(view),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/search`,
      () => HttpResponse.json({ sources: [], next_cursor: null, remaining: 0 }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/read`,
      () =>
        HttpResponse.json({
          source: {
            source_id: "record:material",
            kind: "record",
            title: "材料",
            version: "source-v3",
            locator: {},
          },
          content: "真实资料片段",
          offset: 0,
          next_cursor: null,
          remaining: 0,
        }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/rules`,
      async ({ request }) => {
        writes.push(
          (await request.json()) as components["schemas"]["ContextRuleChange"],
        );
        return HttpResponse.json(
          {
            code: "CONTEXT_VERSION_CONFLICT",
            detail: "设置已变化，请刷新后重试",
          },
          { status: 409 },
        );
      },
    ),
  );
  renderAt(
    `/chat-context/${FIRST_SESSION_ID}?view=sources&source=record%3Amaterial`,
  );
  const button = await screen.findByRole("button", { name: "排除此资料来源" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await screen.findByText(/设置已变化/);
  expect(writes).toEqual([
    {
      action: "EXCLUDE_SOURCE",
      expected_version: 7,
      source_id: "record:material",
      source_version: "source-v3",
    },
  ]);
  expect(screen.queryByText(/设置已保存/)).not.toBeInTheDocument();
});

it("上下文页面固定、编辑和解除提交持久版本，实际与下一轮配置分开", async () => {
  let version = 1;
  let pins: components["schemas"]["ContextPinOut"][] = [];
  const writes: components["schemas"]["ContextPinChange"][] = [];
  const view = () => ({
    session_id: FIRST_SESSION_ID,
    version,
    segment: 1,
    actual_turn_id: null,
    actual: [],
    actual_pins: [],
    pins,
    next_estimate: null,
    next_error_code: null,
  });
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
      HttpResponse.json([chatSession(FIRST_SESSION_ID, { title: "固定验证" })]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`, () =>
      HttpResponse.json(chatSession(FIRST_SESSION_ID, { title: "固定验证" })),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/estimates`,
      () => HttpResponse.json(view()),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/pins`,
      async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["ContextPinChange"];
        writes.push(body);
        if (body.expected_version !== version)
          return HttpResponse.json(
            { code: "CONTEXT_VERSION_CONFLICT", detail: "设置已变化" },
            { status: 409 },
          );
        version++;
        pins =
          body.action === "REMOVE"
            ? []
            : [
                {
                  id: "pin-1",
                  mode: "TEXT",
                  content: body.content,
                  title: body.content,
                  status: "VALID",
                  injected: false,
                  offset: 0,
                },
              ];
        return HttpResponse.json({
          session_id: FIRST_SESSION_ID,
          version,
          pins,
        });
      },
    ),
  );
  renderAt(`/chat-context/${FIRST_SESSION_ID}?view=next`);
  const input = await screen.findByRole("textbox", {
    name: "明确约束或关键决定",
  });
  fireEvent.change(input, { target: { value: "所有例子使用 Python" } });
  fireEvent.click(screen.getByRole("button", { name: "固定内容" }));
  expect(
    await screen.findByText("已保存设置版本 2，从下一轮生效"),
  ).toBeVisible();
  expect(await screen.findByText("所有例子使用 Python")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  fireEvent.change(
    screen.getByRole("textbox", { name: "明确约束或关键决定" }),
    { target: { value: "所有例子使用 TypeScript" } },
  );
  const editForm = screen
    .getByRole("textbox", { name: "明确约束或关键决定" })
    .closest("form");
  if (!editForm) throw new Error("固定编辑表单缺失");
  fireEvent.click(within(editForm).getByRole("button", { name: "更新" }));
  await screen.findByText("已保存设置版本 3，从下一轮生效");
  await screen.findByText("所有例子使用 TypeScript", { selector: "p" });
  fireEvent.click(screen.getByRole("button", { name: "解除固定" }));
  await screen.findByText("已保存设置版本 4，从下一轮生效");
  expect(writes.map((body) => [body.action, body.expected_version])).toEqual([
    ["ADD", 1],
    ["UPDATE", 2],
    ["REMOVE", 3],
  ]);
  fireEvent.click(screen.getByRole("tab", { name: "本轮实际输入" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("textbox", { name: "明确约束或关键决定" }),
    ).not.toBeInTheDocument(),
  );
});

it("来源页面固定选中原文时提交来源身份、版本和原始偏移", async () => {
  const writes: unknown[] = [];
  const view = {
    session_id: FIRST_SESSION_ID,
    version: 7,
    segment: 1,
    actual_turn_id: null,
    actual: [],
    pins: [],
    next_estimate: null,
    next_error_code: null,
  };
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
      HttpResponse.json([chatSession(FIRST_SESSION_ID, {})]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`, () =>
      HttpResponse.json(chatSession(FIRST_SESSION_ID, {})),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/:id/context`, () =>
      HttpResponse.json(view),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/estimates`,
      () => HttpResponse.json(view),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/search`,
      () => HttpResponse.json({ sources: [], next_cursor: null, remaining: 0 }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/read`,
      () =>
        HttpResponse.json({
          source: {
            source_id: "message:original",
            kind: "message",
            title: "来源",
            version: "v3",
            locator: {},
          },
          content: "必须使用 Python",
          offset: 2400,
          next_cursor: null,
          remaining: 0,
        }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/pins`,
      async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json({
          session_id: FIRST_SESSION_ID,
          version: 8,
          pins: [],
        });
      },
    ),
  );
  renderAt(
    `/chat-context/${FIRST_SESSION_ID}?view=sources&source=message%3Aoriginal`,
  );
  const button = await screen.findByRole("button", { name: "固定选中片段" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await screen.findByText("已保存设置版本 8，从下一轮生效");
  expect(writes).toEqual([
    expect.objectContaining({
      expected_version: 7,
      action: "ADD",
      mode: "SNIPPET",
      content: "必须使用 Python",
      source_id: "message:original",
      source_version: "v3",
      offset: 2400,
    }),
  ]);
});

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
  const process = {
    id: "process-live",
    session_id: FIRST_SESSION_ID,
    user_message_id: "user-row",
    assistant_message_id: null as string | null,
    status: "RUNNING",
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ended_at: null as string | null,
    elapsed_ms: 0,
    history_saved: true,
    entries: [] as {
      kind: "tool";
      id: string;
      tool: string;
      query: string;
      status: string;
      hits: number | null;
    }[],
  };
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
      const name = event.split("\n")[0].slice(7);
      const data: Record<string, unknown> = JSON.parse(
        event.split("\ndata: ")[1],
      );
      if (name === "tool_call") {
        const id =
          typeof data.tool_call_id === "string"
            ? data.tool_call_id
            : `call-${process.entries.length}`;
        process.entries.push({
          kind: "tool",
          id,
          tool: String(data.tool),
          query: String(data.query),
          status: "RUNNING",
          hits: null,
        });
        data.tool_call_id = id;
      } else if (name === "tool_result") {
        const entry = process.entries.find(
          (entry) =>
            entry.id === data.tool_call_id ||
            (entry.tool === data.tool && entry.status === "RUNNING"),
        );
        if (entry) {
          entry.status = data.ok ? "SUCCEEDED" : "FAILED";
          entry.hits = Number(data.hits);
          data.tool_call_id = entry.id;
        }
      } else if (name === "done" || name === "error") {
        process.status = name === "done" ? "COMPLETED" : "FAILED";
        process.ended_at = new Date().toISOString();
        if (name === "done")
          process.assistant_message_id = String(data.message_id);
      }
      if (
        ["status", "tool_call", "tool_result", "done", "error"].includes(name)
      )
        data.process = process;
      streamController?.enqueue(
        encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`),
      );
    },
    closeStream: () => streamController?.close(),
  };
}

const TURN_ID = "tttttttt-tttt-4ttt-8ttt-tttttttttttt";

function turnPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: TURN_ID,
    session_id: FIRST_SESSION_ID,
    user_message_id: "user-row",
    status: "RUNNING",
    cancel_requested: false,
    attempt: 1,
    output_revision: 1,
    last_seq: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_text: "",
    ...overrides,
  };
}

/** 轮次契约 mock 四件套：提交 202、事件订阅 SSE、持久取消、快照对账。 */
function turnFlowHandlers(
  makeResponse: () => HttpResponse<DefaultBodyType>,
  onAccept?: () => void,
) {
  const state = { cancelled: false };
  const markCancelled = () => {
    state.cancelled = true;
  };
  const handlers = [
    http.post(
      `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/turns`,
      () => {
        onAccept?.();
        return HttpResponse.json(turnPayload(), { status: 202 });
      },
    ),
    http.get(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/events`, () =>
      makeResponse(),
    ),
    http.post(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/cancel`, () => {
      markCancelled();
      return HttpResponse.json({
        turn: turnPayload({ cancel_requested: true }),
      });
    }),
    http.get(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}`, () =>
      HttpResponse.json(
        turnPayload(
          state.cancelled
            ? {
                status: "CANCELLED",
                cancel_requested: true,
                finished_at: new Date().toISOString(),
              }
            : {},
        ),
      ),
    ),
  ];
  return handlers;
}

afterEach(() => {
  useChatUiStore.setState({ draftsBySession: {} });
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
  vi.mocked(openWebUrl).mockClear();
});

describe("AI 对话", () => {
  it("上下文原文查找、分段续读与失效反馈复用公开读取入口", async () => {
    const source = {
      source_id: "message:original",
      kind: "message",
      title: "早期约束",
      version: "v1",
      locator: {
        message_id: "original",
        quote: "前半段约束",
        start_offset: 8000,
      },
    };
    const reads: unknown[] = [];
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([
          chatSession(FIRST_SESSION_ID, { title: "原文会话" }),
        ]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () =>
          HttpResponse.json(
            chatSession(FIRST_SESSION_ID, { title: "原文会话" }),
          ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/estimates`,
        () =>
          HttpResponse.json({
            session_id: FIRST_SESSION_ID,
            version: 1,
            segment: 1,
            actual_turn_id: null,
            actual: [],
            next_estimate: null,
            next_error_code: null,
          }),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/search`,
        () =>
          HttpResponse.json({
            sources: [source],
            next_cursor: null,
            remaining: 0,
          }),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/read`,
        async ({ request }) => {
          const body =
            (await request.json()) as components["schemas"]["ContextReadRequest"];
          reads.push(body);
          if (body.cursor)
            return HttpResponse.json({
              source,
              content: "后半段约束",
              offset: 2400,
              next_cursor: null,
              remaining: 0,
            });
          return HttpResponse.json({
            source,
            content: "前半段约束",
            offset: 0,
            next_cursor: "next",
            remaining: 600,
          });
        },
      ),
    );
    renderAt(`/chat-context/${FIRST_SESSION_ID}?view=sources`);
    await screen.findByRole("heading", { name: "上下文管理" });
    fireEvent.click(await screen.findByRole("tab", { name: "来源原文" }));
    fireEvent.click(await screen.findByRole("button", { name: /早期约束/ }));
    expect(await screen.findByLabelText("来源正文")).toHaveTextContent(
      "前半段约束",
    );
    expect(reads[0]).toEqual(
      expect.objectContaining({ quote: "前半段约束", offset: 8000 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "继续读取" }));
    await waitFor(() =>
      expect(screen.getByLabelText("来源正文")).toHaveTextContent("后半段约束"),
    );
    expect(reads).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source_id: "message:original",
          version: "v1",
          cursor: "next",
        }),
      ]),
    );
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/:id/context/sources/read`,
        () =>
          HttpResponse.json(
            { code: "CONTEXT_SOURCE_STALE", detail: "来源版本已变化" },
            { status: 409 },
          ),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "从头读取" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "来源版本已变化",
    );
  });
  it("上下文独立页面往返与切换会话保留隔离草稿，草稿不进入 URL", async () => {
    const sessions = [
      chatSession(FIRST_SESSION_ID, { title: "第一会话" }),
      chatSession(SECOND_SESSION_ID, { title: "第二会话" }),
    ];
    const previews: unknown[] = [];
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json(sessions),
      ),
      ...sessions.map((session) =>
        http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${session.id}`, () =>
          HttpResponse.json(session),
        ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/:sessionId/context/estimates`,
        async ({ request, params }) => {
          previews.push(await request.json());
          return HttpResponse.json({
            session_id: params.sessionId,
            version: 1,
            segment: 1,
            actual_turn_id: null,
            actual: [],
            next_estimate: null,
            next_error_code: "MODEL_CAPABILITY_REQUIRED",
          });
        },
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);
    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "第一会话的未发送草稿" } });
    fireEvent.click(screen.getByRole("link", { name: "查看上下文" }));
    expect(
      await screen.findByRole("heading", { name: "上下文管理" }),
    ).toBeVisible();
    expect(window.location.pathname).toBe(`/chat-context/${FIRST_SESSION_ID}`);
    expect(window.location.search).toBe("");
    await waitFor(() =>
      expect(previews).toEqual([
        expect.objectContaining({ content: "第一会话的未发送草稿" }),
      ]),
    );
    fireEvent.click(screen.getByRole("tab", { name: "下一轮预估" }));
    await waitFor(() => expect(window.location.search).toBe("?view=next"));
    expect(
      await screen.findByText(
        "请在 AI 服务设置中配置此端点和模型的输入上限或总窗口。",
      ),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("combobox", { name: "当前会话" }));
    const second = await screen.findByRole("option", { name: "第二会话" });
    fireEvent.pointerDown(second);
    fireEvent.pointerUp(second);
    fireEvent.click(second);
    await waitFor(() =>
      expect(window.location.pathname).toBe(
        `/chat-context/${SECOND_SESSION_ID}`,
      ),
    );
    expect(window.location.search).toBe("?view=next");
    fireEvent.click(screen.getByRole("link", { name: "返回对话" }));
    expect(
      await screen.findByRole("textbox", { name: "提问输入框" }),
    ).toHaveValue("");
    fireEvent.change(screen.getByRole("textbox", { name: "提问输入框" }), {
      target: { value: "第二会话草稿" },
    });
    fireEvent.click(screen.getByRole("link", { name: /第一会话/ }));
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "提问输入框" })).toHaveValue(
        "第一会话的未发送草稿",
      ),
    );
    expect(useChatUiStore.getState().draftsBySession[SECOND_SESSION_ID]).toBe(
      "第二会话草稿",
    );
  });
  it("空态如实展示引导卡，不出现对话列表", async () => {
    renderAt("/chat");

    expect(
      await screen.findByRole("heading", { name: "开始第一场对话" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "开始对话" })).toBeEnabled();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it.each(["general", "knowledge"] as const)(
    "新建菜单选择 %s 后创建固定身份的自由对话",
    async (agentId) => {
      const created = chatSession(FIRST_SESSION_ID, { agent_id: agentId });
      let freeBody: unknown;
      server.use(
        http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
          HttpResponse.json([]),
        ),
        http.post(
          `${TEST_SIDECAR_URL}/api/chat-sessions`,
          async ({ request }) => {
            freeBody = await request.json();
            return HttpResponse.json(created, { status: 201 });
          },
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
      const assistant = await screen.findByRole("menuitemradio", {
        name: agentId === "knowledge" ? /本地知识助手/ : /通用助手/,
      });
      fireEvent.click(assistant);
      expect(assistant).toHaveAttribute("aria-checked", "true");
      // 菜单四入口：自由聊天直达建会话。
      fireEvent.click(
        await screen.findByRole("menuitem", { name: "自由聊天" }),
      );

      await waitFor(() =>
        expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
      );
      expect(freeBody).toEqual({
        agent_id: agentId,
        mode: "ASK",
        scope: "FREE",
      });
      expect(
        await screen.findByRole("textbox", { name: "提问输入框" }),
      ).toBeVisible();
      // 空会话由建议卡承担引导，不再显示旧文案。
      expect(await screen.findByText("你可以这样提问")).toBeVisible();
      if (agentId === "knowledge") {
        expect(screen.getAllByText("本地知识助手").length).toBeGreaterThan(0);
        expect(screen.getByRole("button", { name: "联网搜索" })).toBeDisabled();
        expect(
          screen.queryByRole("combobox", { name: "授权模式" }),
        ).not.toBeInTheDocument();
      }
    },
  );

  it("新建时可挂载收件箱记录，无转写记录置灰并说明原因", async () => {
    const recordId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: recordId,
      scope: "RECORD",
    });
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
    fireEvent.click(await screen.findByRole("menuitem", { name: "挂载记录…" }));
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
    expect(body).toEqual({
      agent_id: "general",
      mode: "ASK",
      record_id: recordId,
    });
    // 对话框已关闭（挂载选择器消失）；会话右栏的授权模式开关是新常驻 combobox，
    // 断言收窄到对话框自身。
    expect(
      screen.queryByRole("combobox", { name: "挂载学习记录（可选）" }),
    ).not.toBeInTheDocument();
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

  it("研究会话在列表行与标题栏展示「研究」徽章，空会话建议卡换研究示例", async () => {
    const research = chatSession(FIRST_SESSION_ID, {
      mode: "RESEARCH",
      scope: "ALL",
      title: "transformer 变体调研",
    });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([research]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => HttpResponse.json(research),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () => HttpResponse.json([]),
      ),
    );

    renderAt("/chat");

    const row = await screen.findByRole("listitem");
    expect(row).toHaveTextContent("研究");

    // 打开会话：标题栏出现「研究」徽章，建议卡换研究特化示例。
    fireEvent.click(screen.getByRole("link", { name: /transformer 变体调研/ }));
    const article = await screen.findByRole("article", {
      name: /transformer 变体调研/,
    });
    expect(within(article).getByText("研究")).toBeVisible();
    expect(await screen.findByText("可以这样开始研究")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /比较多来源观点/ }),
    ).toBeEnabled();
    expect(screen.queryByText("你可以这样提问")).not.toBeInTheDocument();
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
    let accepted = false;
    let answered = false;
    const opened = openSseResponse(
      sseChunks(['event: status\ndata: {"phase":"generating"}']),
    );
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
              : accepted
                ? [SYSTEM_ROW, messageRow("user-row", "USER", "什么是 MVCC")]
                : [SYSTEM_ROW],
          ),
      ),
      ...turnFlowHandlers(
        () => opened.response,
        () => {
          accepted = true;
        },
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "什么是 MVCC" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    // 生成开始就显示已受理的提问，不等首个 token 或 done。
    expect(await screen.findByText("什么是 MVCC")).toBeVisible();
    expect(screen.getByRole("button", { name: "停止" })).toBeVisible();
    opened.pushEvent('event: token\ndata: {"text":"回答"}');
    expect(await screen.findByText("回答")).toBeVisible();
    expect(screen.getAllByText("什么是 MVCC")).toHaveLength(1);
    opened.pushEvent('event: token\ndata: {"text":"完成"}');
    expect(await screen.findByText("回答完成")).toBeVisible();
    answered = true;
    opened.pushEvent(
      'event: done\ndata: {"message_id":"assistant-row","content":"回答完成"}',
    );
    opened.closeStream();
    // done 后发送入口恢复，输入框清空。
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "发送" })).toBeEnabled(),
    );
    expect(screen.getAllByText("什么是 MVCC")).toHaveLength(1);
    expect(input).toHaveValue("");
  });

  it("流式期间出现停止按钮且不可连发，停止后展示重新生成入口", async () => {
    let accepted = false;
    const opened = openSseResponse(
      sseChunks(['event: status\ndata: {"phase":"generating"}']),
    );
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json(
            accepted
              ? [SYSTEM_ROW, messageRow("user-row", "USER", "长问题")]
              : [SYSTEM_ROW],
          ),
      ),
      ...turnFlowHandlers(
        () => opened.response,
        () => {
          accepted = true;
        },
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
    expect(await screen.findByText("长问题")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));
    // 持久取消受理（「正在停止」）；等待态有可见阶段文字，不只可访问名称。
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "正在停止" })).toBeVisible(),
    );
    expect(screen.getByText("正在停止")).toBeVisible();
    opened.pushEvent('event: status\ndata: {"phase":"cancelled"}');
    // 停止丢弃半截文本：流式气泡消失、发送恢复；末尾未回复提问露出重试入口。
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "发送" })).toBeEnabled(),
    );
    expect(screen.getByText("长问题")).toBeVisible();
    expect(screen.getByRole("button", { name: "重新生成回答" })).toBeEnabled();
    opened.closeStream();
  });

  it("停止请求失败就地提示错误，回答仍在继续且可再次停止", async () => {
    let accepted = false;
    const opened = openSseResponse(
      sseChunks(['event: status\ndata: {"phase":"generating"}']),
    );
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json(
            accepted
              ? [SYSTEM_ROW, messageRow("user-row", "USER", "长问题")]
              : [SYSTEM_ROW],
          ),
      ),
      // 取消请求网络未送达：就地错误提示，不静默吞错。同批 use 内靠前者优先，
      // 须排在四件套的成功取消之前。
      http.post(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}/cancel`, () =>
        HttpResponse.error(),
      ),
      ...turnFlowHandlers(
        () => opened.response,
        () => {
          accepted = true;
        },
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "长问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    fireEvent.click(await screen.findByRole("button", { name: "停止" }));

    expect(
      await screen.findByText("停止请求未送达，回答仍在继续；请重试"),
    ).toBeVisible();
    // 取消未受理：未进入停止态，按钮可直接重试。
    expect(screen.getByRole("button", { name: "停止" })).toBeEnabled();

    // 回答自然完成后，停止失败的过时提示清除。
    opened.pushEvent(
      'event: done\ndata: {"message_id":"assistant-row","content":"回答完成"}',
    );
    opened.closeStream();
    await waitFor(() =>
      expect(
        screen.queryByText("停止请求未送达，回答仍在继续；请重试"),
      ).not.toBeInTheDocument(),
    );
  });

  it("快照对账的失败错误经统一翻译入口，英文界面不出现后端中文原文", async () => {
    let accepted = false;
    const opened = openSseResponse([]);
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json(
            accepted
              ? [SYSTEM_ROW, messageRow("user-row", "USER", "长问题")]
              : [SYSTEM_ROW],
          ),
      ),
      // 快照对账读到失败轮次：错误码已登记 i18n，后端原文为中文。
      // 同批 use 内靠前者优先，须排在四件套的快照之前。
      http.get(`${TEST_SIDECAR_URL}/api/chat-turns/${TURN_ID}`, () =>
        HttpResponse.json(
          turnPayload({
            status: "FAILED",
            error_code: "LLM_PROVIDER_UNCONFIGURED",
            error_message: "AI 服务配置已失效，请重新配置后再试",
          }),
        ),
      ),
      ...turnFlowHandlers(
        () => opened.response,
        () => {
          accepted = true;
        },
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "长问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByRole("button", { name: "停止" });

    await applyLanguage("en");
    // 流断开且无终态事件 → 快照对账发现 FAILED：展示登记码的英文译文。
    opened.closeStream();
    expect(
      await screen.findByText(
        "Configure an LLM provider (including its API key) first.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText("AI 服务配置已失效，请重新配置后再试"),
    ).not.toBeInTheDocument();
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
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/turns`,
        () => {
          if (conflict) {
            conflict = false;
            return HttpResponse.json(
              {
                detail:
                  "CHAT_TURN_IN_PROGRESS：该对话正在生成回答，请稍候或先停止",
              },
              { status: 409 },
            );
          }
          return HttpResponse.json(turnPayload(), { status: 202 });
        },
      ),
      ...turnFlowHandlers(() =>
        sseResponse(
          sseChunks([
            'event: status\ndata: {"phase":"generating"}',
            'event: token\ndata: {"text":"好"}',
            'event: done\ndata: {"message_id":"assistant-row","content":"好"}',
          ]),
          () => {
            answered = true;
          },
        ),
      ),
    );
    useSessionPage();

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "第一条" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText(/该对话正在生成回答/)).toBeVisible();

    // 错误后可继续发问。
    fireEvent.change(screen.getByRole("textbox", { name: "提问输入框" }), {
      target: { value: "第二条" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(screen.getByText("好")).toBeVisible());
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
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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

  it("右栏引用超过 4 条时只预览前 4 条，查看全部在弹窗中列出", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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
            messageRow("user-row", "USER", "总结一下"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "根据资料总结如下[1][2][3][4][5][6]。",
              model: "stub-chat-model",
              citations: Array.from({ length: 6 }, (_, position) => ({
                index: position + 1,
                record_id: RECORD_ID,
                quote: `引用条目 ${position + 1}`,
              })),
              created_at: "2026-08-27T08:00:00.000000Z",
            },
          ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    const viewAll = await screen.findByRole("button", {
      name: "查看全部 6 条",
    });
    const panelList = screen.getByRole("list", { name: "引用来源" });
    expect(within(panelList).getAllByRole("listitem")).toHaveLength(4);
    expect(
      within(panelList).queryByRole("button", { name: "[5] 引用条目 5" }),
    ).not.toBeInTheDocument();

    fireEvent.click(viewAll);

    const dialog = await screen.findByRole("dialog");
    const dialogList = within(dialog).getByRole("list", { name: "引用来源" });
    expect(within(dialogList).getAllByRole("listitem")).toHaveLength(6);
    expect(
      within(dialogList).getByRole("button", { name: "[6] 引用条目 6" }),
    ).toBeVisible();
  });

  it("角标无对应引用时保持纯文本，不出现可点击项", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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

  it("检索过程默认仅展示最新状态，done 后保留可展开历史", async () => {
    const answered = { current: false };
    const opened = openSseResponse([]);
    server.use(...turnFlowHandlers(() => opened.response));
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
    expect(screen.queryByText("「MVCC」命中 3 条")).not.toBeInTheDocument();

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
    fireEvent.click(
      await screen.findByRole("button", { name: /已完成.*2 次工具调用/ }),
    );
    expect(screen.getByText("「MVCC」命中 3 条")).toBeVisible();
    expect(screen.getByText("「undo 日志」检索失败")).toBeVisible();
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
    server.use(
      ...turnFlowHandlers(() =>
        sseResponse(
          sseChunks([
            'event: token\ndata: {"text":"答"}',
            'event: done\ndata: {"message_id":"assistant-row","content":"答"}',
          ]),
          () => {
            answered.current = true;
          },
        ),
      ),
    );
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/turns`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(turnPayload(), { status: 202 });
        },
      ),
    );
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
        request_id: expect.any(String),
        page: { page_type: "chat", captured_at: expect.any(String) },
      }),
    );

    // 关闭开关后同一会话再发：标志随开关变化。
    fireEvent.click(webSwitch);
    expect(webSwitch).not.toBeChecked();
    fireEvent.change(input, { target: { value: "不联网问问" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(bodies[1]).toEqual({
        content: "不联网问问",
        web_search: false,
        request_id: expect.any(String),
        page: { page_type: "chat", captured_at: expect.any(String) },
      }),
    );
  });

  it("挂载会话默认关闭：输入区 Globe 打开后与右栏开关同源联动", async () => {
    const RECORD_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
    });
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
        request_id: expect.any(String),
        page: { page_type: "chat", captured_at: expect.any(String) },
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
    server.use(...turnFlowHandlers(() => opened.response));
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
    const created = chatSession(FIRST_SESSION_ID, {
      record_id: RECORD_ID,
      scope: "RECORD",
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

  it("web 引用可发起「建议保存」提案并就地确认入库（零事实变更直至确认）", async () => {
    const WEB_URL = "https://en.wikipedia.org/wiki/Cache_(computing)";
    const PROPOSAL_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const created = chatSession(FIRST_SESSION_ID, { scope: "ALL" });
    let proposalBody: unknown = null;
    let confirmed = false;
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
            messageRow("user-row", "USER", "缓存是什么"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "缓存是高速临时存储[1]。",
              model: "stub-chat-model",
              citations: [
                { index: 1, source: "web", url: WEB_URL, title: "Cache" },
              ],
              created_at: "2026-08-27T08:00:00.000000Z",
            },
          ]),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/proposals`, async ({ request }) => {
        proposalBody = await request.json();
        return HttpResponse.json(
          {
            id: PROPOSAL_ID,
            proposal_type: "RESEARCH_INGEST",
            status: "PENDING",
            session_id: null,
            message_id: null,
            target_type: null,
            target_id: null,
            payload: { url: WEB_URL, title: "Cache" },
            evidence_refs: null,
            error_code: null,
            created_at: "2026-09-19T08:00:00.000000Z",
            decided_at: null,
          },
          { status: 201 },
        );
      }),
      http.post(
        `${TEST_SIDECAR_URL}/api/proposals/${PROPOSAL_ID}/confirm`,
        () => {
          confirmed = true;
          return HttpResponse.json({ status: "APPLIED" });
        },
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    // 建议保存 → 创建 RESEARCH_INGEST 提案（未确认前不动资料事实）
    fireEvent.click(await screen.findByRole("button", { name: "保存为资料" }));
    await waitFor(() =>
      expect(proposalBody).toEqual({
        proposal_type: "RESEARCH_INGEST",
        payload: { url: WEB_URL, title: "Cache" },
      }),
    );
    // 就地确认卡：确认后才经业务入库
    expect(await screen.findByText("保存建议待确认")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
    await waitFor(() => expect(confirmed).toBe(true));
    expect(
      await screen.findByText("已保存到资料库，抓取在后台进行。"),
    ).toBeVisible();
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
            scope: "RECORD",
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
      scope: "RECORD",
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

describe("跨记录问答范围（B2）", () => {
  const COURSE_ID = "11111111-2222-4333-8444-555555555555";

  function courseList() {
    return http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
      HttpResponse.json([
        {
          id: COURSE_ID,
          name: "分布式系统",
          learning_context: "INTEREST",
          status: "ACTIVE",
          created_at: "2026-08-27T08:00:00.000000Z",
          updated_at: "2026-08-27T08:00:00.000000Z",
        },
      ]),
    );
  }

  function scopeSessionPage(session: ChatSessionOut, handlers: HttpHandler[]) {
    server.use(
      ...handlers,
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([session]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${session.id}`, () =>
        HttpResponse.json(session),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${session.id}/messages`,
        () => HttpResponse.json([SYSTEM_ROW]),
      ),
      courseList(),
    );
    renderAt(`/chat/${session.id}`);
  }

  it.each(["general", "knowledge"] as const)(
    "%s 范围切换保留助手身份",
    async (agentId) => {
      const created = chatSession(FIRST_SESSION_ID, {
        scope: "ALL",
        agent_id: agentId,
      });
      let body: unknown;
      scopeSessionPage(chatSession(SECOND_SESSION_ID, { agent_id: agentId }), [
        http.post(
          `${TEST_SIDECAR_URL}/api/chat-sessions`,
          async ({ request }) => {
            body = await request.json();
            return HttpResponse.json(created, { status: 201 });
          },
        ),
      ]);

      fireEvent.click(
        await screen.findByRole("button", {
          name: "切换到全部资料（将新建对话）",
        }),
      );

      await waitFor(() =>
        expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
      );
      expect(body).toEqual({ agent_id: agentId, mode: "ASK", scope: "ALL" });
    },
  );

  it("范围胶囊点「课程」打开选课弹窗，选定后创建 COURSE 会话", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      scope: "COURSE",
      course_id: COURSE_ID,
    });
    let body: unknown;
    scopeSessionPage(chatSession(SECOND_SESSION_ID, {}), [
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions`,
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(created, { status: 201 });
        },
      ),
    ]);

    fireEvent.click(
      await screen.findByRole("button", { name: "切换到课程（将新建对话）" }),
    );
    expect(
      await screen.findByRole("heading", { name: "选择课程" }),
    ).toBeVisible();
    fireEvent.click(await screen.findByRole("button", { name: "分布式系统" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    expect(body).toEqual({
      agent_id: "general",
      mode: "ASK",
      scope: "COURSE",
      course_id: COURSE_ID,
    });
  });

  it("新建菜单「课程问答」与「全部资料」入口可用", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      scope: "COURSE",
      course_id: COURSE_ID,
    });
    let body: unknown;
    server.use(
      courseList(),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions`,
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json(created, { status: 201 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([]),
      ),
    );
    renderAt("/chat");

    fireEvent.click(await screen.findByRole("button", { name: "开始对话" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "课程问答…" }));
    expect(
      await screen.findByRole("heading", { name: "选择课程" }),
    ).toBeVisible();
    fireEvent.click(await screen.findByRole("button", { name: "分布式系统" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    expect(body).toEqual({
      agent_id: "general",
      mode: "ASK",
      scope: "COURSE",
      course_id: COURSE_ID,
    });
  });

  it("课程会话页展示课程名标识与右栏范围卡，webSearch 默认关闭", async () => {
    // 独立 sessionId：webSearchBySession 按会话记忆跨用例存留（Zustand 模块级）。
    const created = chatSession("1a1a1a1a-1a1a-41a1-81a1-1a1a1a1a1a1a", {
      scope: "COURSE",
      course_id: COURSE_ID,
    });
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
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([
          {
            id: "r1",
            title: "第 2 讲",
            course_id: COURSE_ID,
            has_transcript: true,
          },
          {
            id: "r2",
            title: "第 5 讲",
            course_id: COURSE_ID,
            has_transcript: true,
          },
          {
            id: "r3",
            title: "收件箱速记",
            course_id: null,
            has_transcript: true,
          },
        ]),
      ),
    );
    scopeSessionPage(created, []);

    // 标题栏与右栏出现课程名；右栏范围卡显示范围内记录数（只数该课程）。
    expect(
      await screen.findAllByText("分布式系统", { selector: "span" }),
    ).not.toHaveLength(0);
    expect(await screen.findByText("范围内 2 条记录")).toBeVisible();
    // 课程范围视同挂载：联网开关默认关。
    await waitFor(() => {
      const webSwitch = screen.getByRole("switch", { name: "联网搜索" });
      expect(webSwitch).not.toBeChecked();
    });
  });

  it("全部资料会话行与右栏显示范围标识", async () => {
    const created = chatSession(FIRST_SESSION_ID, { scope: "ALL" });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([]),
      ),
    );
    scopeSessionPage(created, []);

    // 标题栏徽标与侧栏行标识（全部资料 span）至少各出现一次。
    expect(
      (await screen.findAllByText("全部资料", { selector: "span" })).length,
    ).toBeGreaterThan(0);
    expect(await screen.findByText("范围内 0 条记录")).toBeVisible();
  });

  it("search_library 工具卡三态文案", async () => {
    const created = chatSession(FIRST_SESSION_ID, { scope: "ALL" });
    scopeSessionPage(created, []);
    const opened = openSseResponse([]);
    server.use(...turnFlowHandlers(() => opened.response));

    const input = await screen.findByRole("textbox", { name: "提问输入框" });
    fireEvent.change(input, { target: { value: "一致性哈希" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    opened.pushEvent('event: status\ndata: {"phase":"generating"}');
    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"search_library","query":"一致性哈希"}',
    );
    expect(
      await screen.findByText("正在检索学习资料「一致性哈希」"),
    ).toBeVisible();

    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"search_library","hits":4,"ok":true}',
    );
    expect(await screen.findByText("「一致性哈希」命中 4 条")).toBeVisible();

    opened.pushEvent(
      'event: tool_call\ndata: {"tool":"search_library","query":"Raft"}',
    );
    opened.pushEvent(
      'event: tool_result\ndata: {"tool":"search_library","hits":0,"ok":false}',
    );
    expect(await screen.findByText("「Raft」检索失败")).toBeVisible();
    opened.closeStream();
  });

  it("跨记录引用显示记录标题，历史行无标题降级为现状", async () => {
    const RECORD_A = "12121212-1212-4121-8121-121212121212";
    const RECORD_B = "13131313-1313-4131-8131-131313131313";
    const created = chatSession(FIRST_SESSION_ID, { scope: "ALL" });
    scopeSessionPage(created, [
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages`,
        () =>
          HttpResponse.json([
            messageRow("user-row", "USER", "对比两次课"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "两次课侧重不同[1][2]。",
              model: "stub-chat-model",
              citations: [
                {
                  index: 1,
                  source: "record",
                  record_id: RECORD_A,
                  record_title: "第 2 讲 一致性哈希",
                  quote: "第二讲聚焦实践",
                },
                {
                  index: 2,
                  source: "record",
                  record_id: RECORD_B,
                  quote: "第五讲聚焦理论",
                },
              ],
              created_at: "2026-08-27T08:00:00.000000Z",
            },
          ]),
      ),
    ]);

    // 跨记录条目：摘录 + 来自《标题》；历史行无 title：降级为「记录」标签。
    expect(await screen.findByText("第二讲聚焦实践")).toBeVisible();
    expect(await screen.findByText("来自《第 2 讲 一致性哈希》")).toBeVisible();
    expect(await screen.findByText("第五讲聚焦理论")).toBeVisible();
    const citationList = screen.getByRole("list", { name: "引用来源" });
    expect(within(citationList).getByText("记录")).toBeVisible();
  });

  it("课程软删后课程会话只读并明示原因", async () => {
    const created = chatSession(FIRST_SESSION_ID, {
      scope: "COURSE",
      course_id: COURSE_ID,
      course_deleted: true,
    });
    scopeSessionPage(created, []);

    expect(await screen.findAllByText("课程已删除")).not.toHaveLength(0);
    const input = screen.getByRole("textbox", { name: "提问输入框" });
    expect(input).toBeDisabled();
    expect(
      screen.getByText("课程已删除，对话已失效，无法继续发送。"),
    ).toBeVisible();
  });
});

describe("对话转知识点（对话转学习资产 V1）", () => {
  const RECORD_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const COURSE_ID = "99999999-9999-4999-8999-999999999999";

  function recordMountSessionPage() {
    const created = chatSession(FIRST_SESSION_ID, {
      scope: "RECORD",
      record_id: RECORD_ID,
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
            messageRow("user-row", "USER", "AOF 是什么"),
            messageRow(
              "assistant-row",
              "ASSISTANT",
              "## AOF 持久化\n\n写入以追加方式进行 [1]。",
              "stub-chat-model",
            ),
          ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([
          {
            id: RECORD_ID,
            title: "第 1 讲 Redis 持久化",
            course_id: COURSE_ID,
            has_transcript: true,
          },
          {
            id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            title: "收件箱速记",
            course_id: null,
            has_transcript: true,
          },
        ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);
  }

  it("AI 回答可保存为知识点：默认挂载记录、预填完整正文、请求体完整", async () => {
    const bodies: object[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}/messages/assistant-row/knowledge-points`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          return HttpResponse.json(
            {
              id: "kp-new",
              record_id: RECORD_ID,
              batch_id: null,
              name: "AOF 持久化",
              detail: "写入以追加方式进行。",
              tags: [],
              importance: 3,
              generated_from_summary_id: null,
              generation_status: "ACTIVE",
              chat_source: null,
              created_at: "2026-08-27T08:00:00.000000Z",
              updated_at: "2026-08-27T08:00:00.000000Z",
            },
            { status: 201 },
          );
        },
      ),
    );
    recordMountSessionPage();

    // 仅 AI 回答携带保存入口（用户消息无）。
    const saveButton = await screen.findAllByRole("button", {
      name: "保存为知识点",
    });
    expect(saveButton).toHaveLength(1);
    fireEvent.click(saveButton[0]);

    // Dialog 打开：详情预填完整正文（标题去标记 + 引用角标去除）。
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("详情")).toHaveValue(
      "AOF 持久化\n\n写入以追加方式进行。",
    );
    fireEvent.change(within(dialog).getByLabelText("名称"), {
      target: { value: "AOF 持久化" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存知识点" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "保存知识点" }),
      ).not.toBeInTheDocument(),
    );
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toEqual({
      name: "AOF 持久化",
      detail: "AOF 持久化\n\n写入以追加方式进行。",
      tags: [],
      importance: 3,
      target_record_id: RECORD_ID,
    });
    expect(
      await screen.findByText("已保存为知识点「AOF 持久化」"),
    ).toBeVisible();
  });

  it("自由会话未选目标记录时提交被拦并提示", async () => {
    const created = chatSession(FIRST_SESSION_ID, { scope: "FREE" });
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
            messageRow("user-row", "USER", "AOF 是什么"),
            messageRow(
              "assistant-row",
              "ASSISTANT",
              "回答正文。",
              "stub-chat-model",
            ),
          ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([
          {
            id: RECORD_ID,
            title: "第 1 讲 Redis 持久化",
            course_id: COURSE_ID,
            has_transcript: true,
          },
        ]),
      ),
    );
    renderAt(`/chat/${FIRST_SESSION_ID}`);

    fireEvent.click(
      await screen.findByRole("button", { name: "保存为知识点" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("名称"), {
      target: { value: "AOF" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存知识点" }));

    expect(within(dialog).getByText("请先选择目标记录")).toBeVisible();
  });
});

describe("资料解读会话（LIBRARY_ITEM，工单 04）", () => {
  const ITEM_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
  const QUOTE = "网页剪藏正文记录了向量检索的取舍";

  function renderItemSession() {
    const created = chatSession(FIRST_SESSION_ID, {
      scope: "LIBRARY_ITEM",
      library_item_id: ITEM_ID,
      title: "网页剪藏正文怎么读？",
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
            messageRow("user-row", "USER", "这篇资料讲了什么？"),
            {
              id: "assistant-row",
              role: "ASSISTANT",
              content: "资料讲向量检索取舍[1]。",
              model: "stub-chat-model",
              citations: [
                {
                  index: 1,
                  source: "library",
                  library_item_id: ITEM_ID,
                  title: "网页剪藏正文",
                  quote: QUOTE,
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
  }

  it("资料范围徽章与 library 引用点击跳转资料来源预览", async () => {
    renderItemSession();

    // 范围徽章 + 右栏挂载卡都以「资料解读」标识范围（LIBRARY_ITEM 不进全局胶囊）。
    const markers = await screen.findAllByText("资料解读");
    expect(markers.length).toBeGreaterThan(0);

    fireEvent.click(
      await screen.findByRole("button", {
        name: `[1] ${QUOTE}（资料：网页剪藏正文），点击查看资料来源`,
      }),
    );
    await waitFor(() => expect(window.location.pathname).toBe("/library"));
    const search = new URLSearchParams(window.location.search);
    expect(search.get("sel")).toBe(ITEM_ID);
    expect(search.get("selType")).toBe("item");
  });
});
