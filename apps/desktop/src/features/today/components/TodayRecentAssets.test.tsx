// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QuickNoteContext } from "@/features/text-capture/QuickNoteContext";
import { TodayRecentAssets } from "@/features/today/components/TodayRecentAssets";
import { useTodayRefresh } from "@/features/today/useTodayRefresh";
import type { AssetType, RecentAsset } from "@/features/today/api/today";
import { Route as TodayRoute } from "@/pages/index";
import { applyLanguage } from "@/i18n";
import { server } from "@/mocks/server";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { renderWithQuery } from "@/test/test-utils";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const endpoint = `${TEST_SIDECAR_URL}/api/today/recent-assets`;
const kinds: AssetType[] = [
  "summary",
  "knowledge_point",
  "quiz",
  "review_material",
];
const rows: RecentAsset[] = Array.from({ length: 25 }, (_, i) => ({
  asset_type: kinds[i % 4],
  record_id: `record-${i}`,
  record_title: `事务学习 ${i}`,
  course_id: "course",
  course_name: "数据库",
  asset_count: i % 4 === 1 ? 8 : 1,
  asset_at: "2026-10-10T08:00:00Z",
  time_basis: i % 4 === 0 ? "confirmed" : "created",
  href: `/records/record-${i}`,
}));

function Workbench() {
  useTodayRefresh();
  return <TodayRecentAssets />;
}
function renderAt(path = "/", capture = vi.fn()) {
  const root = createRootRoute({ component: Outlet });
  const index = createRoute({
    getParentRoute: () => root,
    path: "/",
    validateSearch: TodayRoute.options.validateSearch,
    component: Workbench,
  });
  const records = createRoute({
    getParentRoute: () => root,
    path: "/records/$recordId",
    component: () => <p>来源记录</p>,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, records]),
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const result = renderWithQuery(
    <QuickNoteContext value={capture}>
      <RouterProvider router={router} />
    </QuickNoteContext>,
  );
  return { ...result, router, capture };
}
function serve(getRows = () => rows) {
  server.use(
    http.get(endpoint, ({ request }) => {
      const params = new URL(request.url).searchParams;
      const filtered = getRows().filter(
        (row) =>
          !params.has("asset_type") ||
          row.asset_type === params.get("asset_type"),
      );
      const offset = Number(params.get("offset") ?? 0),
        limit = Number(params.get("limit") ?? 5);
      return HttpResponse.json({
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        offset,
        limit,
      });
    }),
  );
}
afterEach(async () => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  await applyLanguage("zh");
});

describe("近期学习产出", () => {
  it("显示最近五组真实数量、来源和时间依据，可展开翻页并收起", async () => {
    serve();
    const { router } = renderAt();
    const list = await screen.findByRole("list", { name: "近期学习产出列表" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText(/8 个知识点/)).toBeVisible();
    expect(screen.getAllByText(/确认于.*2026/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/创建于.*2026/).length).toBeGreaterThan(0);
    expect(screen.queryByText("示意")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看全部" }));
    await waitFor(() =>
      expect(
        within(screen.getByRole("list")).getAllByRole("listitem"),
      ).toHaveLength(20),
    );
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await screen.findByText("事务学习 24");
    expect(router.state.location.search.assets_page).toBe(2);
    expect(screen.getByRole("heading", { name: "近期学习产出" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "收起" }));
    await screen.findByText("事务学习 0");
    expect(
      within(screen.getByRole("list")).getAllByRole("listitem"),
    ).toHaveLength(5);
    expect(router.state.location.search.assets_page).toBe(1);
  });

  it("URL 恢复类型、展开和页码，切换类型返回第一页", async () => {
    serve();
    const { router } = renderAt("/?assets_expanded=true&assets_page=2");
    await screen.findByText("事务学习 24");
    fireEvent.click(screen.getByRole("combobox", { name: "筛选产出类型" }));
    const option = await screen.findByRole("option", { name: "知识点" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() =>
      expect(router.state.location.search.asset_type).toBe("knowledge_point"),
    );
    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(6),
    );
    expect(router.state.location.search.assets_page).toBe(1);
    expect(router.state.location.search.assets_expanded).toBe(true);
    expect(screen.queryByText(/1 份总结/)).not.toBeInTheDocument();
  });

  it.each(kinds)("%s 分组进入来源记录对应标签", async (kind) => {
    serve(() => rows.filter((row) => row.asset_type === kind).slice(0, 1));
    const { router } = renderAt();
    const link = await screen.findByRole("link", { name: /事务学习/ });
    const expected = {
      summary: undefined,
      knowledge_point: "knowledge-points",
      quiz: "quiz",
      review_material: "review",
    }[kind];
    fireEvent.click(link);
    await screen.findByText("来源记录");
    expect(router.state.location.pathname).toBe(
      `/records/record-${kinds.indexOf(kind)}`,
    );
    expect(
      new URLSearchParams(router.state.location.searchStr).get("tab"),
    ).toBe(expected ?? null);
  });

  it("删除后缩减页数时回退到有效页，前台刷新重新读取", async () => {
    let current = rows;
    serve(() => current);
    const { router } = renderAt("/?assets_expanded=true&assets_page=2");
    await screen.findByText("事务学习 24");
    current = rows.slice(0, 4);
    fireEvent(window, new Event("focus"));
    await waitFor(() =>
      expect(router.state.location.search.assets_page).toBe(1),
    );
    await screen.findByText("事务学习 0");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("空态调用现有捕获入口，读取失败可重试", async () => {
    let failed = true;
    server.use(
      http.get(endpoint, () =>
        failed
          ? HttpResponse.json({ detail: "failed" }, { status: 500 })
          : HttpResponse.json({ items: [], total: 0, offset: 0, limit: 5 }),
      ),
    );
    const { capture } = renderAt();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "近期学习产出暂时无法读取",
    );
    failed = false;
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await screen.findByText("暂无此类学习产出");
    fireEvent.click(screen.getByRole("button", { name: "新建" }));
    expect(capture).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("每分钟读取并支持英文单复数", async () => {
    await applyLanguage("en");
    serve();
    renderAt();
    await screen.findByRole("list", { name: "Recent learning outputs list" });
    expect(screen.getByText(/8 knowledge points/)).toBeVisible();
    expect(screen.getAllByText(/1 summary/).length).toBeGreaterThan(0);
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    // 重新挂载刷新 hook，确保计时器属于可控时钟。
    cleanup();
    const second = renderAt();
    await screen.findByRole("list", { name: "Recent learning outputs list" });
    const spy = vi.spyOn(second.queryClient, "invalidateQueries");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["today", "recent-assets"] });
  });
});
