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
import {
  markRestartPending,
  resetRestartPending,
} from "@/services/restartPending";
import { exitApplication } from "@/services/tauri/lifecycle";

const lifecycle = vi.hoisted(() => ({
  exitRequested: undefined as (() => void) | undefined,
}));

const shortcutRuntime = vi.hoisted(() => ({
  mounted: null as { shortcut: string; onTriggered: () => void } | null,
  available: true,
}));

const closeBehaviorRuntime = vi.hoisted(() => ({
  mounted: null as {
    getBehavior: () => string | null;
    onExitRequested: () => void;
  } | null,
}));

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

// 桌面环境下根路由会先做首启分流：生命周期测试只覆盖完成首启之后的行为。
vi.mock("@/services/tauri/onboarding", () => ({
  isOnboardingRequired: vi.fn(async () => false),
  completeOnboarding: vi.fn(async () => undefined),
}));

vi.mock("@/services/tauri/recording", () => ({
  setRecordingKeepAwake: vi.fn().mockResolvedValue(undefined),
  hideWindowTemporarily: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/services/tauri/lifecycle", () => ({
  isDesktopLifecycleAvailable: () => true,
  listenExitRequested: vi.fn(async (handler: () => void) => {
    lifecycle.exitRequested = handler;
    return () => undefined;
  }),
  exitApplication: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/services/tauri/preferences", () => ({
  mountCloseBehavior: vi.fn(
    async (options: {
      getBehavior: () => string | null;
      onExitRequested: () => void;
    }) => {
      closeBehaviorRuntime.mounted = options;
      return () => undefined;
    },
  ),
  mountQuickNoteShortcut: vi.fn(
    async (shortcut: string, onTriggered: () => void) => {
      shortcutRuntime.mounted = { shortcut, onTriggered };
      return shortcutRuntime.available;
    },
  ),
}));

function renderApp() {
  window.history.replaceState(null, "", "/");
  return render(<App />);
}

async function waitForLifecycleMounts() {
  await waitFor(() => {
    expect(lifecycle.exitRequested).toBeTypeOf("function");
    expect(shortcutRuntime.mounted).not.toBeNull();
  });
}

function triggerQuickNoteShortcut() {
  act(() => shortcutRuntime.mounted?.onTriggered());
}

afterEach(() => {
  lifecycle.exitRequested = undefined;
  shortcutRuntime.mounted = null;
  shortcutRuntime.available = true;
  closeBehaviorRuntime.mounted = null;
  vi.mocked(exitApplication).mockClear();
  resetRestartPending();
});

describe("桌面生命周期", () => {
  it("按偏好注册速记快捷键，重复触发复用同一个速记框、保留正文并恢复正文焦点", async () => {
    renderApp();
    await waitForLifecycleMounts();

    expect(shortcutRuntime.mounted?.shortcut).toBe("Ctrl+Alt+N");

    triggerQuickNoteShortcut();
    const body = await screen.findByLabelText("正文");
    fireEvent.change(body, { target: { value: "不能丢失的速记" } });
    screen.getByRole("button", { name: "保存" }).focus();

    triggerQuickNoteShortcut();

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(body).toHaveValue("不能丢失的速记");
    await waitFor(() => expect(document.activeElement).toBe(body));
  });

  it("快捷键注册失败时只显示一次可理解提示且应用内入口仍可用", async () => {
    shortcutRuntime.available = false;
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
    await waitForLifecycleMounts();

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
    await waitForLifecycleMounts();
    triggerQuickNoteShortcut();
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

  it("数据目录迁移后：录音状态查询失败也直接退出，不被保护提示卡死", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/recording-sessions`, () =>
        HttpResponse.error(),
      ),
    );
    markRestartPending();
    renderApp();
    await waitForLifecycleMounts();

    act(() => lifecycle.exitRequested?.());

    await waitFor(() => expect(exitApplication).toHaveBeenCalledOnce());
    expect(screen.queryByText(/暂时无法确认录音状态/)).not.toBeInTheDocument();
  });

  it("桌面环境挂载关窗分流：偏好贯通且退出请求收敛到安全退出", async () => {
    renderApp();
    await waitForLifecycleMounts();

    await waitFor(() => expect(closeBehaviorRuntime.mounted).not.toBeNull());
    expect(closeBehaviorRuntime.mounted?.getBehavior()).toBe("TRAY");

    act(() => closeBehaviorRuntime.mounted?.onExitRequested());

    await waitFor(() => expect(exitApplication).toHaveBeenCalledOnce());
  });
});
