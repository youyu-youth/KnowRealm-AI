// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import "@/i18n";
import { applyTheme } from "@/features/settings/appearance";
import { TodayStatsBand } from "@/features/today/components/TodayStatsBand";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));
vi.mock("@/charts/BaseChart", () => ({
  BaseChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel} />
  ),
}));

afterEach(() => {
  document.documentElement.classList.remove("light", "dark");
  delete document.documentElement.dataset.theme;
});

it("主题变化保留统计折叠状态和图表节点", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <TodayStatsBand />
    </QueryClientProvider>,
  );
  const toggle = await screen.findByRole("button", { name: "累计学习统计" });
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  const chart = screen.getByRole("img", { name: "学习趋势图" });
  act(() =>
    applyTheme("DARK", {
      theme: "DARK",
      light_theme_id: "LIGHT_SAGE",
      dark_theme_id: "DARK_INK",
    }),
  );
  expect(document.documentElement).toHaveAttribute("data-theme-switching");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "累计学习统计" }),
    ).toHaveAttribute("aria-expanded", "false"),
  );
  expect(screen.getByRole("img", { name: "学习趋势图" })).toBe(chart);
  await waitFor(() =>
    expect(document.documentElement).not.toHaveAttribute(
      "data-theme-switching",
    ),
  );
  view.unmount();
  client.clear();
});
