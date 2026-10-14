// @vitest-environment jsdom

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { useSidebarUiStore } from "@/components/layout/sidebarUiStore";
import { preferencesPayload, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: TEST_SIDECAR_URL,
    token: "test-launch-token",
  }),
}));

const url = `${TEST_SIDECAR_URL}/api/settings/preferences`;

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  server.use(
    http.get(
      `${TEST_SIDECAR_URL}/api/settings/data-directory/library-state`,
      () => HttpResponse.json({ empty_library: false }),
    ),
  );
});

afterEach(() => {
  useSidebarUiStore.setState({ collapsed: false, width: null });
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Desktop 布局切换", () => {
  it("保存后切换布局、保留草稿及侧栏宽度", async () => {
    let current = { ...preferencesPayload };
    const patches: object[] = [];
    server.use(
      http.get(url, () => HttpResponse.json(current)),
      http.put(url, async ({ request }) => {
        const patch = (await request.json()) as object;
        patches.push(patch);
        current = { ...current, ...patch };
        return HttpResponse.json(current);
      }),
    );
    useSidebarUiStore.setState({ width: 280 });
    window.history.replaceState(null, "", "/settings");
    render(<App />);
    const nickname = await screen.findByLabelText("昵称");
    fireEvent.change(nickname, { target: { value: "未保存的布局测试草稿" } });
    fireEvent.click(screen.getByRole("tab", { name: "外观与布局" }));
    fireEvent.click(await screen.findByRole("radio", { name: "顶部导航布局" }));
    const navigation = await screen.findByRole("navigation", {
      name: "工作区导航",
    });
    expect(
      within(navigation).getByRole("link", { name: "资产库" }),
    ).toHaveAttribute("href", "/library");
    expect(document.getElementById("app-sidebar")).toHaveAttribute("hidden");
    expect(screen.queryByRole("button", { name: "收起侧边栏" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "打开档案设置" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "设置" })).toBeInTheDocument();
    expect(nickname).toHaveValue("未保存的布局测试草稿");
    expect(nickname).toBeInTheDocument();
    expect(useSidebarUiStore.getState().width).toBe(280);
    expect(patches).toEqual([{ layout_mode: "TOP" }]);
  });

  it("切回侧栏恢复既有宽度", async () => {
    let current = { ...preferencesPayload, layout_mode: "TOP" };
    server.use(
      http.get(url, () => HttpResponse.json(current)),
      http.put(url, async ({ request }) => {
        current = { ...current, ...((await request.json()) as object) };
        return HttpResponse.json(current);
      }),
    );
    useSidebarUiStore.setState({ width: 280 });
    window.history.replaceState(null, "", "/settings?section=appearance");
    render(<App />);
    await screen.findByRole("navigation", { name: "工作区导航" });
    fireEvent.click(screen.getByRole("radio", { name: "侧边栏布局" }));
    await screen.findByRole("button", { name: "收起侧边栏" });
    expect(useSidebarUiStore.getState().width).toBe(280);
    expect(
      screen.getByRole("separator", { name: "调整侧边栏宽度" }),
    ).toHaveAttribute("aria-valuenow", "280");
  });

  it("保存失败保持原布局，并能通过错误提示重试", async () => {
    let current = { ...preferencesPayload };
    let fail = true;
    server.use(
      http.get(url, () => HttpResponse.json(current)),
      http.put(url, async ({ request }) => {
        const patch = (await request.json()) as object;
        if (fail)
          return HttpResponse.json(
            { detail: "保存失败", code: "INTERNAL_ERROR" },
            { status: 500 },
          );
        current = { ...current, ...patch };
        return HttpResponse.json(current);
      }),
    );
    window.history.replaceState(null, "", "/settings?section=appearance");
    render(<App />);
    fireEvent.click(await screen.findByRole("radio", { name: "顶部导航布局" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "服务器内部错误",
    );
    expect(screen.getByRole("radio", { name: "侧边栏布局" })).toBeChecked();
    expect(document.getElementById("app-sidebar")).not.toHaveAttribute(
      "hidden",
    );
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByRole("navigation", { name: "工作区导航" });
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("启动顶部布局后，窄窗溢出菜单可导航，扩宽后恢复菜单项", async () => {
    let width = 340;
    const observers: Array<() => void> = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          observers.push(() => callback([], this));
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(
      function (this: Element) {
        if (this.tagName === "NAV") return new DOMRect(0, 0, width, 36);
        if (this.parentElement?.getAttribute("aria-hidden") === "true") {
          return new DOMRect(
            0,
            0,
            this === this.parentElement.lastElementChild ? 36 : 100,
            36,
          );
        }
        return new DOMRect(0, 0, 100, 36);
      },
    );
    let current = { ...preferencesPayload, layout_mode: "TOP" };
    server.use(
      http.get(url, () => HttpResponse.json(current)),
      http.put(url, async ({ request }) => {
        current = { ...current, ...((await request.json()) as object) };
        return HttpResponse.json(current);
      }),
    );
    window.history.replaceState(null, "", "/inbox");
    render(<App />);
    const more = await screen.findByRole("button", { name: "更多导航" });
    fireEvent.click(more);
    fireEvent.click(await screen.findByRole("menuitem", { name: "资产库" }));
    await waitFor(() => expect(window.location.pathname).toBe("/library"));
    width = 1200;
    act(() => observers.forEach((notify) => notify()));
    expect(screen.queryByRole("button", { name: "更多导航" })).toBeNull();
    const navigation = within(
      screen.getByRole("navigation", { name: "工作区导航" }),
    );
    expect(navigation.getByRole("link", { name: "资产库" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      navigation.getByRole("button", { name: "学习画像（未接入）" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "近期课程" }),
    ).toBeInTheDocument();
  });
});
