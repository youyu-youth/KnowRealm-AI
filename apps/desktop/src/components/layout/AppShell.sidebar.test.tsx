// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { useSidebarUiStore } from "@/components/layout/sidebarUiStore";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const PREFERENCES = {
  theme: "SYSTEM",
  font_scale: "M",
  timezone: null,
  close_behavior: "TRAY",
  quick_note_shortcut: "Ctrl+Alt+N",
  autostart: false,
  quiz_last_count: 5,
  last_route: null,
};

function renderApp() {
  window.history.replaceState(null, "", "/");
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
      HttpResponse.json(PREFERENCES),
    ),
  );
  return render(<App />);
}

afterEach(() => {
  // Zustand 是模块级状态，逐用例复位，避免折叠态跨用例存留。
  useSidebarUiStore.setState({ collapsed: false, width: null });
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("标题栏侧边栏切换", () => {
  it("右缘拖拽限制宽度，Toggle 后恢复拖拽宽度与课程状态", async () => {
    renderApp();
    const sidebar = await screen.findByRole("complementary", {
      name: "工作区导航",
    });
    const handle = screen.getByRole("separator", { name: "调整侧边栏宽度" });
    vi.spyOn(sidebar, "getBoundingClientRect").mockImplementation(
      () => new DOMRect(0, 0, useSidebarUiStore.getState().width ?? 224, 700),
    );
    Object.defineProperty(handle, "setPointerCapture", { value: vi.fn() });
    Object.defineProperty(handle, "hasPointerCapture", { value: () => true });
    Object.defineProperty(handle, "releasePointerCapture", { value: vi.fn() });
    const pointer = (type: string, clientX: number, button = 0) => {
      const event = new MouseEvent(type, { bubbles: true, clientX, button });
      Object.defineProperty(event, "pointerId", { value: 1 });
      fireEvent(handle, event);
    };
    pointer("pointerdown", 224, 2);
    pointer("pointermove", 300);
    expect(useSidebarUiStore.getState().width).toBeNull();
    handle.focus();
    expect(handle).toHaveFocus();
    pointer("pointerdown", 224);
    expect(handle).not.toHaveFocus();
    pointer("pointermove", -100);
    expect(handle).toHaveAttribute("aria-valuenow", "64");
    pointer("pointermove", 150);
    expect(handle).toHaveAttribute("aria-valuenow", "150");
    pointer("pointermove", 500);
    expect(handle).toHaveAttribute("aria-valuenow", "360");
    pointer("pointermove", 280);
    pointer("pointerup", 280);
    expect(handle).not.toHaveFocus();
    pointer("pointermove", 350);
    expect(handle).toHaveAttribute("aria-valuenow", "280");
    expect(document.documentElement).not.toHaveClass("sidebar-resizing");

    const courses = screen.getByRole("button", { name: "近期课程" });
    fireEvent.click(courses);
    fireEvent.click(screen.getByRole("button", { name: "收起侧边栏" }));
    expect(
      screen.queryByRole("separator", { name: "调整侧边栏宽度" }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "展开侧边栏" }));
    expect(
      screen.getByRole("separator", { name: "调整侧边栏宽度" }),
    ).toHaveAttribute("aria-valuenow", "280");
    expect(courses).toHaveAttribute("aria-expanded", "false");
  });

  it("分隔条支持键盘调节且不吞掉 Tab", async () => {
    renderApp();
    const handle = await screen.findByRole("separator", {
      name: "调整侧边栏宽度",
    });
    handle.focus();
    fireEvent.keyDown(handle, { key: "End" });
    expect(handle).toHaveFocus();
    expect(handle).toHaveAttribute("aria-valuenow", "360");
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "344");
    fireEvent.keyDown(handle, { key: "Home" });
    expect(handle).toHaveAttribute("aria-valuenow", "64");
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "64");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(handle).toHaveAttribute("aria-valuenow", "80");
    expect(fireEvent.keyDown(handle, { key: "Tab" })).toBe(true);
  });

  it("取消、丢失捕获、窗口失焦与隐藏侧栏都会终止拖拽", async () => {
    renderApp();
    const sidebar = await screen.findByRole("complementary", {
      name: "工作区导航",
    });
    const handle = screen.getByRole("separator", { name: "调整侧边栏宽度" });
    vi.spyOn(sidebar, "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 0, 224, 700),
    );
    Object.defineProperty(handle, "setPointerCapture", { value: vi.fn() });
    Object.defineProperty(handle, "hasPointerCapture", { value: () => true });
    Object.defineProperty(handle, "releasePointerCapture", { value: vi.fn() });
    const pointer = (type: string) => {
      const event = new MouseEvent(type, {
        bubbles: true,
        clientX: 224,
        button: 0,
      });
      Object.defineProperty(event, "pointerId", { value: 1 });
      fireEvent(handle, event);
    };
    for (const type of [
      "pointercancel",
      "lostpointercapture",
      "blur",
      "Escape",
    ]) {
      pointer("pointerdown");
      expect(document.documentElement).toHaveClass("sidebar-resizing");
      if (type === "blur") fireEvent.blur(window);
      else if (type === "Escape") fireEvent.keyDown(handle, { key: "Escape" });
      else pointer(type);
      expect(document.documentElement).not.toHaveClass("sidebar-resizing");
      pointer("pointermove");
      expect(useSidebarUiStore.getState().width).toBeNull();
    }
    pointer("pointerdown");
    fireEvent.click(screen.getByRole("button", { name: "收起侧边栏" }));
    expect(document.documentElement).not.toHaveClass("sidebar-resizing");
  });

  it("收起与恢复侧栏，且折叠不重置侧栏内部状态", async () => {
    renderApp();
    const sidebar = await screen.findByRole("complementary", {
      name: "工作区导航",
    });
    const collapse = screen.getByRole("button", { name: "收起侧边栏" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    expect(sidebar).not.toHaveAttribute("inert");

    // 先改变一个侧栏内部状态：折叠「近期课程」区。
    const courses = screen.getByRole("button", { name: "近期课程" });
    fireEvent.click(courses);
    expect(courses).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(collapse);
    const expand = screen.getByRole("button", { name: "展开侧边栏" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    // 折叠只做视觉裁切：侧栏保持挂载且移出焦点/读屏树。
    expect(sidebar).toHaveAttribute("inert");
    expect(document.body.contains(sidebar)).toBe(true);

    fireEvent.click(expand);
    expect(screen.getByRole("button", { name: "收起侧边栏" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(sidebar).not.toHaveAttribute("inert");
    expect(screen.getByRole("button", { name: "近期课程" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
