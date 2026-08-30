// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const FULL_PREFERENCES = {
  theme: "SYSTEM",
  font_scale: "M",
  timezone: null,
  close_behavior: "TRAY",
  quick_note_shortcut: "Ctrl+Alt+N",
  autostart: false,
  quiz_last_count: 5,
  last_route: null,
};

const putBodies: Array<Record<string, unknown>> = [];

function mockPreferences(lastRoute: string | null) {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
      HttpResponse.json({ ...FULL_PREFERENCES, last_route: lastRoute }),
    ),
  );
}

function mockPutPreferences() {
  putBodies.length = 0;
  server.use(
    http.put(
      `${TEST_SIDECAR_URL}/api/settings/preferences`,
      async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        putBodies.push(body);
        return HttpResponse.json({ ...FULL_PREFERENCES, ...body });
      },
    ),
  );
}

function renderApp() {
  window.history.replaceState(null, "", "/");
  return render(<App />);
}

async function waitForTodayPage() {
  await screen.findByRole("heading", { name: "今日" });
}

function clickNav(name: string) {
  fireEvent.click(screen.getByRole("link", { name }));
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("上次界面恢复", () => {
  it("重启后恢复到上次停留的页面", async () => {
    mockPreferences("/inbox");
    renderApp();

    await screen.findByRole("heading", { name: "收件箱" });
    expect(window.location.pathname).toBe("/inbox");
  });

  it("上次页面已不存在时由 NotFound 兜底", async () => {
    mockPreferences("/gone");
    renderApp();

    await screen.findByRole("heading", { name: "页面不存在" });
    expect(window.location.pathname).toBe("/gone");
  });

  it("导航写入 last_route、回到默认页写 null、设置页不参与记忆", async () => {
    mockPreferences(null);
    mockPutPreferences();
    renderApp();
    await waitForTodayPage();
    expect(putBodies).toEqual([]);

    clickNav("收件箱");
    await screen.findByRole("heading", { name: "收件箱" });
    await waitFor(() => expect(putBodies).toEqual([{ last_route: "/inbox" }]));

    clickNav("设置");
    await screen.findByRole("heading", { name: "设置" });
    await waitFor(() => expect(window.location.pathname).toBe("/settings"));
    expect(putBodies).toEqual([{ last_route: "/inbox" }]);

    clickNav("今日");
    await waitForTodayPage();
    await waitFor(() =>
      expect(putBodies).toEqual([
        { last_route: "/inbox" },
        { last_route: null },
      ]),
    );
  });
});
