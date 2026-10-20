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

async function selectStatus(name: string) {
  fireEvent.click(screen.getByRole("combobox", { name: "任务状态" }));
  const option = await screen.findByRole("option", { name });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
}

describe("今日真实进展", () => {
  it("首屏只显示三项，查看更多打开全部卡片，关闭返回原入口", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
        HttpResponse.json(
          Array.from({ length: 8 }, (_, index) => ({
            ...item,
            item_id: `task-${index}`,
            content: `学习任务 ${index + 1}`,
          })),
        ),
      ),
      http.get(endpoint, () =>
        HttpResponse.json({ ...progress, pending_count: 8 }),
      ),
    );
    renderAt();
    expect(
      await screen.findByRole("link", { name: "学习任务 1" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "学习任务 4" }),
    ).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: /查看更多/ });
    fireEvent.click(more);
    const dialog = await screen.findByRole("dialog", { name: "今日计划项" });
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(8);
    expect(
      within(dialog).getByRole("link", { name: "学习任务 8" }),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: "完成计划项「学习任务 8」" }),
    ).toBeEnabled();
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(more).toHaveFocus());
    expect(
      screen.queryByRole("link", { name: "学习任务 8" }),
    ).not.toBeInTheDocument();
  });

  it("窗口内完成失败保留卡片，成功后同步列表，最后一项完成后可关闭空窗口", async () => {
    let done = false;
    let fail = true;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
        HttpResponse.json(done ? [] : [item]),
      ),
      http.get(endpoint, () =>
        HttpResponse.json({
          ...progress,
          pending_count: done ? 0 : 1,
          completed_count: done ? 1 : 0,
        }),
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
    fireEvent.click(await screen.findByRole("button", { name: /查看更多/ }));
    const dialog = await screen.findByRole("dialog", { name: "今日计划项" });
    const complete = within(dialog).getByRole("button", { name: /完成计划项/ });
    fireEvent.click(complete);
    await waitFor(() => expect(complete).toBeEnabled());
    expect(
      within(dialog).getByRole("link", { name: item.content }),
    ).toBeVisible();
    fail = false;
    fireEvent.click(complete);
    await waitFor(() =>
      expect(within(dialog).getByRole("status")).toHaveTextContent(
        "暂无待完成计划项",
      ),
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "关闭计划项窗口" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "待办事项" })).toHaveFocus(),
    );
    expect(screen.getByRole("combobox", { name: "任务状态" })).toBeVisible();
  });

  it("窗口与侧栏共享课程筛选和排序 URL 状态", async () => {
    const other = {
      ...item,
      item_id: "other-task",
      course_id: "other-course",
      course_name: "数据库",
      content: "比较隔离级别",
      estimated_minutes: 90,
    };
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
        HttpResponse.json([item, other]),
      ),
      http.get(endpoint, () =>
        HttpResponse.json({
          ...progress,
          pending_count: 2,
          courses: [
            ...progress.courses,
            { course_id: other.course_id, course_name: other.course_name },
          ],
        }),
      ),
    );
    const { router } = renderAt();
    fireEvent.click(await screen.findByRole("button", { name: /查看更多/ }));
    const dialog = await screen.findByRole("dialog", { name: "今日计划项" });
    fireEvent.click(within(dialog).getByRole("combobox", { name: "任务排序" }));
    const duration = await screen.findByRole("option", { name: "预估时长 ↓" });
    fireEvent.pointerDown(duration);
    fireEvent.pointerUp(duration);
    fireEvent.click(duration);
    await waitFor(() =>
      expect(router.state.location.search.order).toBe("duration"),
    );
    expect(within(dialog).getAllByRole("listitem")[0]).toHaveTextContent(
      other.content,
    );
    fireEvent.click(
      within(dialog).getByRole("combobox", { name: "按课程筛选" }),
    );
    const option = await screen.findByRole("option", { name: "数据库" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() =>
      expect(router.state.location.search.course).toBe(other.course_id),
    );
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(
      within(dialog).getByRole("button", { name: "关闭计划项窗口" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: other.content })).toBeVisible();
    expect(
      screen.queryByRole("link", { name: item.content }),
    ).not.toBeInTheDocument();
  });

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
    expect(
      screen.getByRole("combobox", { name: "任务状态" }),
    ).toHaveTextContent("待完成 1");
    expect(screen.getByLabelText("今日计划进展")).toHaveTextContent(
      "今日已完成0",
    );
    fail = false;
    fireEvent.click(checkbox);
    await waitFor(() =>
      expect(screen.getByLabelText("今日计划进展")).toHaveTextContent(
        "今日已完成1",
      ),
    );
    await selectStatus("已完成 1");
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
    expect(
      screen.getByRole("combobox", { name: "任务状态" }),
    ).toHaveTextContent("已完成 21");
    fireEvent.click(screen.getByRole("button", { name: /查看更多/ }));
    await screen.findByRole("dialog", { name: "今日已完成计划项" });
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "上一页" }));
    expect(
      await within(screen.getByRole("dialog")).findByText("第一页任务"),
    ).toBeVisible();
    expect(router.state.location.search.completed_page).toBe(1);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
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
    fireEvent.click(screen.getByRole("button", { name: /查看更多/ }));
    const nextPage = await screen.findByRole("button", { name: "下一页" });
    nextPage.focus();
    fireEvent.click(nextPage);
    expect(
      await within(screen.getByRole("dialog")).findByText("第二页任务"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "上一页" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
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
      await screen.findByRole("combobox", { name: "任务状态" }),
    ).toBeVisible();
    expect(router.state.location.search.course).toBe(item.course_id);
    expect(requests.some((query) => query.includes("offset=20"))).toBe(true);
  });

  it("已完成仅预览三项，查看更多保留本页所有事项并恢复焦点", async () => {
    server.use(
      http.get(endpoint, () =>
        HttpResponse.json({
          ...progress,
          completed_count: 8,
          completed_items: Array.from({ length: 8 }, (_, index) => ({
            ...item,
            item_id: `done-${index}`,
            content: `已完成任务 ${index + 1}`,
            plan_version: 1,
            completed_at: "2026-10-15T06:00:00Z",
          })),
        }),
      ),
    );
    const { router } = renderAt();
    await screen.findByRole("combobox", { name: "任务状态" });
    await waitFor(() =>
      expect(screen.getByLabelText("今日计划进展")).toHaveTextContent(
        "今日已完成8",
      ),
    );
    await selectStatus("已完成 8");
    await waitFor(() =>
      expect(router.state.location.search.action_status).toBe("done"),
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByText("已完成任务 4")).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: /查看更多/ });
    fireEvent.click(more);
    const dialog = await screen.findByRole("dialog", {
      name: "今日已完成计划项",
    });
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(8);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(more).toHaveFocus());
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
    expect(
      screen.getByRole("combobox", { name: "任务状态" }),
    ).toHaveTextContent("待完成 —");
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
    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: "任务状态" }),
      ).toHaveTextContent("已完成 21"),
    );
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
    await selectStatus("待完成 0");
    expect(
      await screen.findByText("暂无待完成计划项，可在课程中制定学习计划。"),
    ).toBeVisible();
    expect(
      screen.queryByText("示例任务，不会写入学习计划"),
    ).not.toBeInTheDocument();
  });
});
