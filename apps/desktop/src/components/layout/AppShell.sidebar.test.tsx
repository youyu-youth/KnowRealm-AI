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
  useSidebarUiStore.setState({ collapsed: false });
  window.history.replaceState(null, "", "/");
});

describe("标题栏侧边栏切换", () => {
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
