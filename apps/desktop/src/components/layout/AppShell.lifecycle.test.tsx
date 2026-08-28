// @vitest-environment jsdom

import {
  act,
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
import { exitApplication } from "@/services/tauri/lifecycle";

const lifecycle = vi.hoisted(() => ({
  openQuickNote: undefined as (() => void) | undefined,
  exitRequested: undefined as (() => void) | undefined,
  shortcutAvailable: true,
}));

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

vi.mock("@/services/tauri/lifecycle", () => ({
  isDesktopLifecycleAvailable: () => true,
  getDesktopLifecycleStatus: vi.fn(async () => ({
    shortcutAvailable: lifecycle.shortcutAvailable,
  })),
  listenOpenQuickNote: vi.fn(async (handler: () => void) => {
    lifecycle.openQuickNote = handler;
    return () => undefined;
  }),
  listenExitRequested: vi.fn(async (handler: () => void) => {
    lifecycle.exitRequested = handler;
    return () => undefined;
  }),
  exitApplication: vi.fn().mockResolvedValue(undefined),
}));

function renderApp() {
  window.history.replaceState(null, "", "/");
  return render(<App />);
}

async function waitForLifecycleListeners() {
  await waitFor(() => {
    expect(lifecycle.openQuickNote).toBeTypeOf("function");
    expect(lifecycle.exitRequested).toBeTypeOf("function");
  });
}

afterEach(() => {
  lifecycle.openQuickNote = undefined;
  lifecycle.exitRequested = undefined;
  lifecycle.shortcutAvailable = true;
  vi.mocked(exitApplication).mockClear();
});

describe("桌面生命周期", () => {
  it("重复快捷键复用同一个速记框、保留正文并恢复正文焦点", async () => {
    renderApp();
    await waitForLifecycleListeners();

    act(() => lifecycle.openQuickNote?.());
    const body = await screen.findByLabelText("正文");
    fireEvent.change(body, { target: { value: "不能丢失的速记" } });
    screen.getByRole("button", { name: "保存" }).focus();

    act(() => lifecycle.openQuickNote?.());

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(body).toHaveValue("不能丢失的速记");
    await waitFor(() => expect(document.activeElement).toBe(body));
  });

  it("快捷键注册失败时只显示一次可理解提示且应用内入口仍可用", async () => {
    lifecycle.shortcutAvailable = false;
    renderApp();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ctrl+Alt+N 已被其他应用占用或无法注册",
    );
    expect(screen.getAllByText(/Ctrl\+Alt\+N/)).toHaveLength(1);

    fireEvent.click(await screen.findByRole("button", { name: "新建速记" }));
    expect(
      await screen.findByRole("heading", { name: "新建速记" }),
    ).toBeVisible();
  });

  it("没有活动录音和未保存正文时直接退出", async () => {
    renderApp();
    await waitForLifecycleListeners();

    act(() => lifecycle.exitRequested?.());

    await waitFor(() => expect(exitApplication).toHaveBeenCalledOnce());
    expect(
      screen.queryByRole("heading", { name: "退出 KnowRealm？" }),
    ).not.toBeInTheDocument();
  });

  it("合并活动录音和未保存正文风险，取消保留数据，确认后退出", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/recording-sessions`, () =>
        HttpResponse.json([
          {
            id: "recording-1",
            course_id: null,
            title: "操作系统课堂录音",
            started_at: "2026-08-28T01:00:00.000000Z",
            updated_at: "2026-08-28T01:00:20.000000Z",
            state: "RECORDING",
            recorded_duration_ms: 20_000,
            chunk_count: 1,
          },
        ]),
      ),
    );
    renderApp();
    await waitForLifecycleListeners();
    act(() => lifecycle.openQuickNote?.());
    const body = await screen.findByLabelText("正文");
    fireEvent.change(body, { target: { value: "尚未保存的正文" } });

    act(() => lifecycle.exitRequested?.());

    expect(
      await screen.findByRole("heading", { name: "退出 KnowRealm？" }),
    ).toBeVisible();
    expect(screen.getByText(/最新尚未提交的内存分片可能丢失/)).toBeVisible();
    expect(screen.getByText(/未保存的速记或粘贴正文将丢失/)).toBeVisible();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "取消退出" }));
    expect(
      screen.queryByRole("heading", { name: "退出 KnowRealm？" }),
    ).not.toBeInTheDocument();
    expect(body).toHaveValue("尚未保存的正文");
    expect(exitApplication).not.toHaveBeenCalled();

    act(() => lifecycle.exitRequested?.());
    await screen.findByRole("heading", { name: "退出 KnowRealm？" });
    fireEvent.click(screen.getByRole("button", { name: "确认退出" }));
    expect(exitApplication).toHaveBeenCalledOnce();
  });
});
