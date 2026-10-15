// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
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
import { Route as TodayRoute } from "@/pages/index";
import { TodayActions } from "@/features/today/components/TodayActions";
import { useTodayRefresh } from "@/features/today/useTodayRefresh";
import type { TodayPlanItem, TodayProgress } from "@/features/today/api/today";
import { todayKeys } from "@/features/today/api/keys";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const endpoint = `${TEST_SIDECAR_URL}/api/today/progress`;
const item: TodayPlanItem = {
  item_id: "33333333-3333-4333-8333-333333333333",
  plan_id: "22222222-2222-4222-8222-222222222222",
  course_id: "11111111-1111-4111-8111-111111111111",
  course_name: "响应式编程",
  goal_id: "44444444-4444-4444-8444-444444444444",
  goal_title: "学会 WebFlux",
  action_type: "STUDY_RECORD",
  content: "阅读调度器",
  scheduled_date: "2026-10-15",
  estimated_minutes: 30,
  user_locked: false,
};
const progress: TodayProgress = {
  date: "2026-10-15",
  day_start: "2026-10-14T16:00:00Z",
  day_end: "2026-10-15T16:00:00Z",
  completed_count: 0,
  pending_count: 1,
  overdue_count: 1,
  remaining_estimated_minutes: 30,
  unestimated_count: 0,
  courses: [{ course_id: item.course_id, course_name: item.course_name }],
  completed_items: [],
  offset: 0,
  limit: 20,
};

function Workbench() {
  useTodayRefresh();
  return (
    <TodayActions
      summaries={[]}
      loading={false}
      error={false}
      onRetry={() => {}}
      onFocus={() => {}}
    />
  );
}

function renderAt(path = "/") {
  const root = createRootRoute({ component: Outlet });
  const index = createRoute({
    getParentRoute: () => root,
    path: "/",
    validateSearch: TodayRoute.options.validateSearch,
    component: Workbench,
  });
  const router = createRouter({
    routeTree: root.addChildren([index]),
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const rendered = renderWithQuery(<RouterProvider router={router} />);
  return { ...rendered, router };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("今日真实进展", () => {
  it("完成失败保留原项，成功后更新概览及只读完成列表", async () => {
    let done = false;
    let fail = true;
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({
          ...progress,
          pending_count: done ? 0 : 1,
          overdue_count: done ? 0 : 1,
          remaining_estimated_minutes: done ? 0 : 30,
          completed_count: done ? 1 : 0,
          completed_items: done
            ? [
                {
                  ...item,
                  plan_version: 2,
                  completed_at: "2026-10-15T06:00:00Z",
                },
              ]
            : [],
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
        HttpResponse.json(done ? [] : [item]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/courses/${item.course_id}/plans/${item.plan_id}/items/${item.item_id}/complete`,
        () => {
          if (fail)
            return HttpResponse.json({ detail: "failed" }, { status: 500 });
          done = true;
          return HttpResponse.json({});
        },
      ),
    );
    renderAt();
    const checkbox = await screen.findByRole("checkbox", {
      name: /完成计划项/,
    });
    fireEvent.click(checkbox);
    await waitFor(() => expect(checkbox).toBeEnabled());
    expect(checkbox).not.toBeChecked();
    expect(screen.getByRole("tab", { name: "待完成 1" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "今日已完成 0" })).toBeVisible();
    fail = false;
    fireEvent.click(checkbox);
    const completed = await screen.findByRole("tab", { name: "今日已完成 1" });
    fireEvent.click(completed);
    expect(
      await screen.findByRole("list", { name: "今日已完成计划项" }),
    ).toHaveTextContent("阅读调度器");
    expect(screen.getByText(/计划 v2/)).toBeVisible();
    expect(screen.getByRole("link", { name: "打开课程计划" })).toHaveAttribute(
      "href",
      `/spaces/${item.course_id}?tab=plan`,
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("从 URL 恢复状态和分页，课程与排序变化重置页码，完成独有课程可筛选", async () => {
    const requests: string[] = [];
    server.use(
      http.get(endpoint, ({ request }) => {
        const url = new URL(request.url);
        requests.push(url.search);
        const scoped = url.searchParams.has("course_id");
        const offset = Number(url.searchParams.get("offset"));
        return HttpResponse.json({
          ...progress,
          pending_count: 0,
          overdue_count: 0,
          remaining_estimated_minutes: 0,
          completed_count: scoped ? 1 : 21,
          offset,
          completed_items: [
            {
              ...item,
              content: offset ? "第二页任务" : "第一页任务",
              completed_at: "2026-10-15T06:00:00Z",
              plan_version: 1,
            },
          ],
        });
      }),
    );
    const { router } = renderAt("/?action_status=done&completed_page=2");
    expect(await screen.findByText("第二页任务")).toBeVisible();
    expect(screen.getByRole("tab", { name: "今日已完成 21" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "上一页" }));
    expect(await screen.findByText("第一页任务")).toBeVisible();
    expect(router.state.location.search.completed_page).toBe(1);
    fireEvent.click(screen.getByRole("combobox", { name: "任务排序" }));
    const durationOption = await screen.findByRole("option", {
      name: "预估时长 ↓",
    });
    fireEvent.pointerDown(durationOption);
    fireEvent.pointerUp(durationOption);
    fireEvent.click(durationOption);
    await waitFor(() =>
      expect(router.state.location.search.order).toBe("duration"),
    );
    const nextPage = await screen.findByRole("button", { name: "下一页" });
    nextPage.focus();
    fireEvent.click(nextPage);
    expect(await screen.findByText("第二页任务")).toBeVisible();
    expect(screen.getByRole("button", { name: "上一页" })).toHaveFocus();
    fireEvent.click(screen.getByRole("combobox", { name: "按课程筛选" }));
    const courseOption = await screen.findByRole("option", {
      name: "响应式编程",
    });
    fireEvent.pointerDown(courseOption);
    fireEvent.pointerUp(courseOption);
    fireEvent.click(courseOption);
    await waitFor(() =>
      expect(router.state.location.search.completed_page).toBe(1),
    );
    expect(
      await screen.findByRole("tab", { name: "今日已完成 1" }),
    ).toBeVisible();
    expect(router.state.location.search.course).toBe(item.course_id);
    expect(requests.some((query) => query.includes("offset=20"))).toBe(true);
  });

  it("无估时与部分估时如实显示；请求失败不伪造零值，局部重试恢复", async () => {
    let failure = false;
    let partial = false;
    server.use(
      http.get(endpoint, () =>
        failure
          ? HttpResponse.json({ detail: "failed" }, { status: 500 })
          : HttpResponse.json({
              ...progress,
              remaining_estimated_minutes: partial ? 30 : null,
              unestimated_count: 1,
            }),
      ),
    );
    const { queryClient } = renderAt();
    expect(await screen.findByText("待估时")).toBeVisible();
    expect(screen.getByText(/另有 1 项未估时/)).toBeVisible();
    failure = true;
    await act(() =>
      queryClient.invalidateQueries({
        queryKey: todayKeys.progress("all", "date", 1),
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "今日进展暂时无法读取",
    );
    expect(screen.getByRole("tab", { name: "今日已完成 —" })).toBeVisible();
    failure = false;
    partial = true;
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("30 分钟")).toBeVisible();
    expect(screen.getByText(/另有 1 项未估时/)).toBeVisible();
  });

  it("零任务展示真实空态，后台不刷新，回前台跨日刷新并重置分页", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 15, 23, 59));
    let reads = 0;
    server.use(
      http.get(endpoint, () => {
        reads += 1;
        return HttpResponse.json({
          ...progress,
          pending_count: 0,
          overdue_count: 0,
          remaining_estimated_minutes: 0,
          completed_count: 21,
          completed_items: [],
        });
      }),
    );
    const { router } = renderAt("/?action_status=done&completed_page=2");
    await screen.findByRole("tab", { name: "今日已完成 21" });
    const baseline = reads;
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    expect(reads).toBe(baseline);
    vi.setSystemTime(new Date(2026, 9, 16, 0, 1));
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() =>
      expect(router.state.location.search.completed_page).toBe(1),
    );
    await waitFor(() => expect(reads).toBeGreaterThan(baseline));
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({
          ...progress,
          completed_count: 0,
          pending_count: 0,
          overdue_count: 0,
          remaining_estimated_minutes: 0,
        }),
      ),
    );
    fireEvent(window, new Event("focus"));
    expect(await screen.findByText("今天还没有完成的计划项。")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "待完成 0" }));
    expect(
      await screen.findByText("暂无待完成计划项，可在课程中制定学习计划。"),
    ).toBeVisible();
    expect(
      screen.queryByText("示例任务，不会写入学习计划"),
    ).not.toBeInTheDocument();
  });
});
