// @vitest-environment jsdom

import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { isTauri } from "@tauri-apps/api/core";
import { WindowTitleBar } from "@/components/layout/WindowTitleBar";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { mountCloseBehavior } from "@/services/tauri/preferences";
import { renderWithQuery } from "@/test/test-utils";

const runtime = vi.hoisted(() => ({
  resize: undefined as (() => void) | undefined,
  focus: undefined as (() => void) | undefined,
  closeRequested: undefined as
    ((event: { preventDefault: () => void }) => void) | undefined,
  isFocused: vi.fn(),
  isMaximized: vi.fn(),
  onResized: vi.fn(),
  onFocusChanged: vi.fn(),
  unlistenResize: vi.fn(),
  unlistenFocus: vi.fn(),
  minimize: vi.fn(),
  toggleMaximize: vi.fn(),
  close: vi.fn(),
  hide: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(() => true) }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    ...runtime,
    onCloseRequested: async (handler: typeof runtime.closeRequested) => {
      runtime.closeRequested = handler;
      return () => undefined;
    },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(isTauri).mockReturnValue(true);
  runtime.isFocused.mockResolvedValue(true);
  runtime.isMaximized.mockResolvedValue(false);
  runtime.minimize.mockResolvedValue(undefined);
  runtime.toggleMaximize.mockResolvedValue(undefined);
  runtime.close.mockImplementation(async () => {
    runtime.closeRequested?.({ preventDefault: vi.fn() });
  });
  runtime.closeRequested = undefined;
  runtime.onResized.mockImplementation(async (handler: () => void) => {
    runtime.resize = handler;
    return runtime.unlistenResize;
  });
  runtime.onFocusChanged.mockImplementation(async (handler: () => void) => {
    runtime.focus = handler;
    return runtime.unlistenFocus;
  });
});

describe("自定义窗口标题栏", () => {
  it("模态弹层打开时窗口控制仍可访问，点击不会关闭弹层", async () => {
    renderWithQuery(
      <>
        <WindowTitleBar />
        <Dialog defaultOpen>
          <DialogContent>
            <DialogTitle>未保存内容</DialogTitle>
          </DialogContent>
        </Dialog>
      </>,
    );
    expect(
      await screen.findByRole("dialog", { name: "未保存内容" }),
    ).toBeVisible();
    const minimize = screen.getByRole("button", { name: "最小化" });
    fireEvent.mouseDown(minimize);
    fireEvent.click(minimize);
    expect(runtime.minimize).toHaveBeenCalledOnce();
    expect(screen.getByRole("dialog", { name: "未保存内容" })).toBeVisible();
  });
  it("菜单和全局导航仅占位，窗口操作调用原生 API", async () => {
    renderWithQuery(<WindowTitleBar />);
    for (const name of ["文件", "编辑", "视图", "帮助", "返回", "前进"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    fireEvent.click(screen.getByRole("button", { name: "最小化" }));
    fireEvent.click(screen.getByRole("button", { name: "最大化" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭窗口" }));
    await waitFor(() => expect(runtime.close).toHaveBeenCalledOnce());
    expect(runtime.minimize).toHaveBeenCalledOnce();
    expect(runtime.toggleMaximize).toHaveBeenCalledOnce();
  });

  it("恢复已最大化窗口，并跟随原生尺寸和焦点变化", async () => {
    runtime.isMaximized.mockResolvedValue(true);
    const { unmount } = renderWithQuery(<WindowTitleBar />);
    fireEvent.click(await screen.findByRole("button", { name: "还原窗口" }));
    expect(runtime.toggleMaximize).toHaveBeenCalledOnce();
    runtime.isMaximized.mockResolvedValue(false);
    runtime.isFocused.mockResolvedValue(false);
    await act(async () => {
      runtime.resize?.();
      runtime.focus?.();
    });
    expect(screen.getByRole("button", { name: "最大化" })).toBeEnabled();
    expect(screen.getByRole("banner", { name: "窗口标题栏" })).toHaveAttribute(
      "data-focused",
      "false",
    );
    unmount();
    expect(runtime.unlistenResize).toHaveBeenCalledOnce();
    expect(runtime.unlistenFocus).toHaveBeenCalledOnce();
  });

  it.each(["TRAY", "EXIT"] as const)(
    "关闭按钮保留 %s 分流",
    async (behavior) => {
      const onExitRequested = vi.fn();
      await mountCloseBehavior({
        getBehavior: () => behavior,
        onExitRequested,
      });
      renderWithQuery(<WindowTitleBar />);
      fireEvent.click(screen.getByRole("button", { name: "关闭窗口" }));
      await waitFor(() => expect(runtime.close).toHaveBeenCalledOnce());
      expect(runtime.hide).toHaveBeenCalledTimes(behavior === "TRAY" ? 1 : 0);
      expect(onExitRequested).toHaveBeenCalledTimes(
        behavior === "EXIT" ? 1 : 0,
      );
    },
  );

  it("原生调用失败时提示可重试，不产生未处理的 rejection", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    runtime.minimize.mockRejectedValueOnce(new Error("denied"));
    renderWithQuery(<WindowTitleBar />);
    fireEvent.click(screen.getByRole("button", { name: "最小化" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "窗口操作失败，请重试。",
    );
    fireEvent.click(screen.getByRole("button", { name: "最小化" }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
    log.mockRestore();
  });

  it("卸载后才完成的监听注册也会清理", async () => {
    let resolveFocus: ((unlisten: () => void) => void) | undefined;
    runtime.onFocusChanged.mockReturnValueOnce(
      new Promise<() => void>((resolve) => {
        resolveFocus = resolve;
      }),
    );
    const { unmount } = renderWithQuery(<WindowTitleBar />);
    unmount();
    await act(async () => {
      resolveFocus?.(runtime.unlistenFocus);
    });
    expect(runtime.unlistenResize).toHaveBeenCalledOnce();
    expect(runtime.unlistenFocus).toHaveBeenCalledOnce();
  });

  it("普通浏览器中保留标题栏并禁用窗口控制", () => {
    vi.mocked(isTauri).mockReturnValue(false);
    renderWithQuery(<WindowTitleBar />);
    for (const name of ["最小化", "最大化", "关闭窗口"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    expect(runtime.onResized).not.toHaveBeenCalled();
  });
});
