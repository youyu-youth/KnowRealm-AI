// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  screen,
  within,
} from "@testing-library/react";
import { focusManager } from "@tanstack/react-query";
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
import { TodayMaterialPreparation } from "@/features/today/components/TodayMaterialPreparation";
import { useTodayRefresh } from "@/features/today/useTodayRefresh";
import type {
  LibraryItemOut,
  LibraryItemListOut,
} from "@/features/library/api/library";
import { libraryKeys } from "@/features/library/api/keys";
import { RECENT_MATERIALS_PARAMS } from "@/features/today/api/today";
import { Route as TodayRoute } from "@/pages/index";
import { server } from "@/mocks/server";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { renderWithQuery } from "@/test/test-utils";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: TEST_SIDECAR_URL,
    token: "test-launch-token",
  }),
}));
const endpoint = `${TEST_SIDECAR_URL}/api/library/items`;
const item: LibraryItemOut = {
  id: "source-1",
  course_id: null,
  course_name: null,
  source_type: "DOCUMENT",
  title: "数据库事务讲义",
  origin_uri: null,
  local_path: "files/lecture.pdf",
  mime_type: "application/pdf",
  file_size: 120,
  content_hash: "hash",
  fetched_at: null,
  source_metadata: {},
  schema_version: 1,
  favorite: false,
  status: "ACTIVE",
  created_at: "2026-10-20T08:00:00Z",
  updated_at: "2026-10-20T09:00:00Z",
  deleted_at: null,
  availability: "RETRIEVABLE",
};
function Workbench() {
  useTodayRefresh();
  return <TodayMaterialPreparation />;
}
function renderAt() {
  const root = createRootRoute({ component: Outlet });
  const index = createRoute({
    getParentRoute: () => root,
    path: "/",
    validateSearch: TodayRoute.options.validateSearch,
    component: Workbench,
  });
  const library = createRoute({
    getParentRoute: () => root,
    path: "/library",
    component: () => <p>资料详情</p>,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, library]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return { ...renderWithQuery(<RouterProvider router={router} />), router };
}
function serve(
  items: LibraryItemOut[],
  backfill: LibraryItemListOut["backfill"] = null,
) {
  server.use(
    http.get(endpoint, ({ request }) => {
      const params = new URL(request.url).searchParams;
      expect(params.get("order")).toBe("created");
      expect(params.get("limit")).toBe("3");
      return HttpResponse.json({
        items: items.slice(0, 3),
        total: items.length,
        backfill,
      });
    }),
  );
}
afterEach(() => {
  cleanup();
  focusManager.setFocused(undefined);
  vi.useRealTimers();
  vi.restoreAllMocks();
});
describe("今日最近资料", () => {
  it.each([0, 1, 3, 5])("%i 条入库资料只展示实际最近三条", async (count) => {
    serve(
      Array.from({ length: count }, (_, i) => ({
        ...item,
        id: `source-${i}`,
        title: `资料 ${i}`,
      })),
    );
    renderAt();
    if (count === 0)
      expect(await screen.findByText("暂无最近资料")).toBeVisible();
    else
      expect(
        within(
          await screen.findByRole("list", { name: "最近资料列表" }),
        ).getAllByRole("listitem"),
      ).toHaveLength(Math.min(count, 3));
    const region = screen.getByRole("region", { name: "最近资料" });
    expect(within(region).queryByText("示意")).not.toBeInTheDocument();
    expect(
      within(region).queryByText(/docker-compose.yml/),
    ).not.toBeInTheDocument();
  });
  it.each([
    ["DOCUMENT", "文档"],
    ["WEB", "网页"],
    ["AUDIO", "音频"],
    ["BOOK", "书籍"],
    ["TEXT", "文本"],
  ] as const)(
    "%s 展示真实标题、类型与入库时间并链接资料详情",
    async (source_type, label) => {
      serve([{ ...item, source_type }]);
      renderAt();
      const list = await screen.findByRole("list", { name: "最近资料列表" });
      const link = within(list).getByRole("link");
      expect(link).toHaveTextContent(item.title);
      expect(link).toHaveTextContent(label);
      expect(link).toHaveAttribute(
        "href",
        "/library?domain=sources&selType=item&sel=source-1",
      );
      expect(within(link).getByTitle(item.title)).toBeVisible();
      expect(link.querySelector("time")).toHaveAttribute(
        "datetime",
        item.created_at,
      );
      expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    },
  );
  it("请求失败显示重试而非空态，重试后读取真实数据", async () => {
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({ detail: "failed" }, { status: 500 }),
      ),
    );
    renderAt();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "最近资料暂时无法读取",
    );
    expect(screen.queryByText("暂无最近资料")).not.toBeInTheDocument();
    serve([item]);
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(await screen.findByText(item.title)).toBeVisible();
  });
  it("重新进入页面强制读取新数据，即使旧缓存仍新鲜", async () => {
    serve([item]);
    const { router, queryClient } = renderAt();
    queryClient.setQueryDefaults(libraryKeys.all, { staleTime: Infinity });
    await screen.findByText(item.title);
    await act(() => router.navigate({ to: "/library" }));
    serve([{ ...item, title: "刚导入的新资料" }]);
    await act(() => router.navigate({ to: "/" }));
    expect(await screen.findByText("刚导入的新资料")).toBeVisible();
  });
  it("回到前台与分钟刷新更新列表，隐藏时不刷新", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    serve([item]);
    renderAt();
    await screen.findByText(item.title);
    serve([{ ...item, title: "分钟刷新资料" }]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(await screen.findByText("分钟刷新资料")).toBeVisible();
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    serve([{ ...item, title: "前台刷新资料" }]);
    fireEvent(window, new Event("focus"));
    expect(screen.queryByText("前台刷新资料")).not.toBeInTheDocument();
    visibility.mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    expect(await screen.findByText("前台刷新资料")).toBeVisible();
  });
  it.each(["processing", "backfill"])(
    "%s 期间轮询，终态与后台停止轮询",
    async (mode) => {
      vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
      focusManager.setFocused(true);
      serve(
        [
          {
            ...item,
            availability: mode === "processing" ? "PROCESSING" : "RETRIEVABLE",
          },
        ],
        mode === "backfill" ? { status: "RUNNING", progress: 0.2 } : null,
      );
      const { queryClient } = renderAt();
      await screen.findByText(item.title);
      if (mode === "processing")
        expect(screen.getByText("处理中")).toBeVisible();
      serve([{ ...item, availability: "FAILED" }]);
      focusManager.setFocused(false);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(screen.queryByText("失败")).not.toBeInTheDocument();
      focusManager.setFocused(true);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(await screen.findByText("失败")).toBeVisible();
      serve([{ ...item, title: "不应自动读到" }]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(screen.queryByText("不应自动读到")).not.toBeInTheDocument();
      await act(() =>
        queryClient.invalidateQueries({
          queryKey: libraryKeys.items(RECENT_MATERIALS_PARAMS),
        }),
      );
      expect(await screen.findByText("不应自动读到")).toBeVisible();
    },
  );
});
