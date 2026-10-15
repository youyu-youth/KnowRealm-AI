// @vitest-environment jsdom
import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
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
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { TodayContinueLearning } from "@/features/today/components/TodayContinueLearning";
import { ChatMarkdown } from "@/features/chat/ChatMarkdown";
import { useLearningVisit } from "@/features/today/useLearningVisit";
import {
  useLearningResumeActions,
  type LearningResume,
} from "@/features/today/api/resume";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

const endpoint = "http://127.0.0.1:43127/api/today/continue-learning";
const id = "12345678-1234-1234-1234-123456789abc";
const entry: LearningResume = {
  kind: "RECORD",
  target_id: id,
  title: "WebFlux 原文",
  record_tab: "transcript",
  course_id: null,
  course_name: null,
  visited_at: "2026-10-15T01:00:00Z",
  answered_count: null,
  total_count: null,
  href: `/records/${id}?tab=transcript`,
};

function renderRouter(component = TodayContinueLearning) {
  const root = createRootRoute({ component: Outlet });
  const index = createRoute({
    getParentRoute: () => root,
    path: "/",
    component,
  });
  const records = createRoute({
    getParentRoute: () => root,
    path: "/records/$recordId",
    component: () => <p>恢复后的原文</p>,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, records]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  renderWithQuery(<RouterProvider router={router} />);
  return router;
}

describe("真实继续学习", () => {
  it("无历史时展示引导，不展示原固定课程", async () => {
    renderRouter();
    expect(await screen.findByText(/打开学习记录、未交卷测验/)).toBeVisible();
    expect(screen.queryByText("操作系统 · 进程与线程")).not.toBeInTheDocument();
  });
  it("继续按钮通过 Router 恢复具体记录与 Tab", async () => {
    server.use(http.get(endpoint, () => HttpResponse.json([entry])));
    const router = renderRouter();
    fireEvent.click(await screen.findByRole("link", { name: "继续阅读" }));
    expect(await screen.findByText("恢复后的原文")).toBeVisible();
    expect(router.state.location.href).toBe(entry.href);
  });
  it("移除失败保留条目，重试成功；清空可取消、确认后清除", async () => {
    let entries = [entry];
    let fail = true;
    let failClear = true;
    let clears = 0;
    server.use(
      http.get(endpoint, () => HttpResponse.json(entries)),
      http.delete(`${endpoint}/RECORD/${id}`, () => {
        if (fail)
          return HttpResponse.json(
            { code: "INTERNAL_ERROR", detail: "failed" },
            { status: 500 },
          );
        entries = [];
        return new HttpResponse(null, { status: 204 });
      }),
      http.delete(endpoint, () => {
        if (failClear) return new HttpResponse(null, { status: 500 });
        clears++;
        entries = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const router = renderRouter();
    fireEvent.click(
      await screen.findByRole("button", { name: /移除.*WebFlux/ }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "续学记录未能更新",
    );
    expect(screen.getByText(entry.title!)).toBeVisible();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: /移除.*WebFlux/ }));
    expect(await screen.findByText(/打开学习记录、未交卷测验/)).toBeVisible();
    entries = [entry];
    await act(() => router.invalidate());
    // 首页未重建时主动刷新查询，通过重新挂载验证返回后的服务器事实。
    await act(() =>
      router.navigate({ to: "/records/$recordId", params: { recordId: id } }),
    );
    await act(() => router.navigate({ to: "/" }));
    fireEvent.click(await screen.findByRole("button", { name: "清空记录" }));
    fireEvent.click(await screen.findByRole("button", { name: "取消" }));
    expect(clears).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "清空记录" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "清空记录" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "续学记录未能更新",
    );
    expect(entries).toHaveLength(1);
    failClear = false;
    fireEvent.click(within(dialog).getByRole("button", { name: "清空记录" }));
    expect(await screen.findByText(/打开学习记录、未交卷测验/)).toBeVisible();
    expect(clears).toBe(1);
  });
  it("查询失败只影响本区并可重试", async () => {
    let fail = true;
    server.use(
      http.get(endpoint, () =>
        fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json([]),
      ),
    );
    renderRouter();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "暂时无法读取续学记录",
    );
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(await screen.findByText(/打开学习记录、未交卷测验/)).toBeVisible();
  });
  it("Agent 返回的白名单链接通过站内 Router 打开", async () => {
    const router = renderRouter(() => (
      <ChatMarkdown content={`[继续原文](${entry.href})`} citations={[]} />
    ));
    fireEvent.click(await screen.findByRole("link", { name: "继续原文" }));
    expect(await screen.findByText("恢复后的原文")).toBeVisible();
    expect(router.state.location.href).toBe(entry.href);
  });
});

function VisitProbe({
  ready,
  tab = "summary",
}: {
  ready: boolean;
  tab?: "summary" | "transcript";
}) {
  useLearningVisit({ kind: "RECORD", target_id: id, record_tab: tab }, ready);
  const mutation = useLearningResumeActions();
  return (
    <button onClick={() => mutation.mutate({ action: "clear" })}>clear</button>
  );
}

describe("访问记录采集", () => {
  it("成功展示与 Tab 变化才记录，普通重渲染和后台刷新不记录", async () => {
    const visits: unknown[] = [];
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    server.use(
      http.put(endpoint, async ({ request }) => {
        visits.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const view = renderWithQuery(<VisitProbe ready={false} />);
    expect(visits).toHaveLength(0);
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <VisitProbe ready />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(visits).toHaveLength(1));
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <VisitProbe ready />
      </QueryClientProvider>,
    );
    await act(() => view.queryClient.invalidateQueries());
    expect(visits).toHaveLength(1);
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <VisitProbe ready tab="transcript" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(visits).toHaveLength(2));
    expect(visits[1]).toMatchObject({ record_tab: "transcript" });
    vi.restoreAllMocks();
  });
  it("隐藏时不写入，回前台后写入；清空等待此前访问提交", async () => {
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    let finish: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const calls: string[] = [];
    server.use(
      http.put(endpoint, async () => {
        calls.push("visit-start");
        await gate;
        calls.push("visit-end");
        return new HttpResponse(null, { status: 204 });
      }),
      http.delete(endpoint, () => {
        calls.push("clear");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithQuery(<VisitProbe ready />);
    expect(calls).toEqual([]);
    visibility.mockReturnValue("visible");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await waitFor(() => expect(calls).toEqual(["visit-start"]));
    fireEvent.click(screen.getByRole("button", { name: "clear" }));
    expect(calls).toEqual(["visit-start"]);
    finish();
    await waitFor(() =>
      expect(calls).toEqual(["visit-start", "visit-end", "clear"]),
    );
    vi.restoreAllMocks();
  });
});
