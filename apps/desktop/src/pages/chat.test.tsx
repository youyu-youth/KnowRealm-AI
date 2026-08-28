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
    created_at: "2026-08-27T08:00:00.000000Z",
    updated_at: "2026-08-27T08:00:00.000000Z",
    ...overrides,
  };
}

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
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
    expect(screen.getByRole("button", { name: "新建自由对话" })).toBeEnabled();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("新建自由对话后立即进入会话页，并明确展示消息功能未接入", async () => {
    const created = chatSession(FIRST_SESSION_ID, {});
    server.use(
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

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${FIRST_SESSION_ID}`),
    );
    expect(
      await screen.findByRole("heading", { name: "消息功能未接入" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "新对话" })).toBeVisible();
    // 无死按钮、无假输入框：当前版本没有发送入口。
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "发送" }),
    ).not.toBeInTheDocument();
  });

  it("列表按最近更新排序，重命名即时生效", async () => {
    let renamed = false;
    const first = chatSession(FIRST_SESSION_ID, { title: "线程调度答疑" });
    const second = chatSession(SECOND_SESSION_ID, { title: "文件系统速记" });
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json(
          renamed
            ? [
                chatSession(FIRST_SESSION_ID, {
                  title: "操作系统答疑",
                  updated_at: "2026-08-27T09:00:00.000000Z",
                }),
                second,
              ]
            : [second, first],
        ),
      ),
      http.patch(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${FIRST_SESSION_ID}`,
        () => {
          renamed = true;
          return HttpResponse.json(
            chatSession(FIRST_SESSION_ID, {
              title: "操作系统答疑",
              updated_at: "2026-08-27T09:00:00.000000Z",
            }),
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
