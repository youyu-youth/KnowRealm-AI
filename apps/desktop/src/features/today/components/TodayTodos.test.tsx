// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

type TodaySummaryTodo = components["schemas"]["TodaySummaryTodoOut"];
type TodayPlanItem = components["schemas"]["TodayPlanItemOut"];

const PENDING_URL = `${TEST_SIDECAR_URL}/api/today/pending-summaries`;
const PLAN_ITEMS_URL = `${TEST_SIDECAR_URL}/api/today/plan-items`;

const COURSE_ID = "9fa85f64-5717-4562-b3fc-2c963f66afa6";
const OTHER_COURSE_ID = "8fa85f64-5717-4562-b3fc-2c963f66afa6";

const todo: TodaySummaryTodo = {
  record_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  title: "新录音 1",
  course_id: COURSE_ID,
  course_name: "langchain学习",
  ready_at: "2026-09-09T08:00:00Z",
};

function todayStr(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

const planItem: TodayPlanItem = {
  item_id: "item-1",
  plan_id: "21111111-1111-4111-8111-111111111111",
  course_id: COURSE_ID,
  course_name: "langchain学习",
  goal_id: "11111111-1111-4111-8111-111111111111",
  goal_title: "掌握 LangChain",
  action_type: "STUDY_RECORD",
  content: "通读 LCEL 转写笔记",
  estimated_minutes: 30,
  scheduled_date: todayStr(),
  user_locked: false,
};

const overdueItem: TodayPlanItem = {
  ...planItem,
  item_id: "item-2",
  course_id: OTHER_COURSE_ID,
  course_name: "操作系统",
  content: "复习进程调度概念",
  estimated_minutes: 20,
  scheduled_date: todayStr(-2),
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/services/tauri/recording", () => ({
  setRecordingKeepAwake: vi.fn().mockResolvedValue(undefined),
  hideWindowTemporarily: vi.fn().mockResolvedValue(undefined),
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/today/progress`, () =>
      HttpResponse.json({
        date: todayStr(),
        day_start: new Date().toISOString(),
        day_end: new Date().toISOString(),
        completed_count: 0,
        pending_count: 2,
        overdue_count: 1,
        remaining_estimated_minutes: 50,
        unestimated_count: 0,
        completed_items: [],
        offset: 0,
        limit: 20,
        courses: [planItem, overdueItem].map(({ course_id, course_name }) => ({
          course_id,
          course_name,
        })),
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${todo.record_id}/summary`, () =>
      HttpResponse.json({ summary: null, action_required: "NONE" }),
    ),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

// 计划项在待办事项中，待确认总结在左侧待处理列表中。
function actionFlow(): HTMLElement {
  const heading = screen.getByRole("heading", { name: "待办事项" });
  const card = heading.closest("section");
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

describe("今日待学双源清单", () => {
  it("按 URL 恢复课程筛选与时长排序，仅呈现匹配的真实计划项", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json([
          planItem,
          overdueItem,
          {
            ...planItem,
            item_id: "long-item",
            content: "深入练习 LCEL",
            estimated_minutes: 60,
          },
        ]),
      ),
    );
    window.history.replaceState(
      null,
      "",
      `/?course=${COURSE_ID}&order=duration`,
    );
    render(<App />);
    const list = await screen.findByRole("list", {
      name: "今日待学计划项列表",
    });
    expect(
      within(list)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["深入练习 LCEL", "通读 LCEL 转写笔记"]);
    expect(
      within(list).queryByText("复习进程调度概念"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: "按课程筛选" }));
    const option = await screen.findByRole("option", { name: "操作系统" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() =>
      expect(
        within(list)
          .getAllByRole("link")
          .map((link) => link.textContent),
      ).toEqual(["复习进程调度概念"]),
    );
    expect(new URLSearchParams(window.location.search).get("course")).toBe(
      OTHER_COURSE_ID,
    );
  });

  it("快捷按钮与右键菜单联动专注，拖放仅接受当前列表任务且不打断本轮", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json([planItem, overdueItem]),
      ),
    );
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "专注此任务「通读 LCEL 转写笔记」",
      }),
    );
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("task")).toBe(
        planItem.item_id,
      ),
    );
    expect(screen.getByRole("heading", { name: "当前专注" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    const second = screen
      .getByRole("link", { name: overdueItem.content })
      .closest("li")!;
    fireEvent.contextMenu(second.querySelector("[data-selected]")!);
    fireEvent.click(
      await screen.findByRole("menuitem", {
        name: "专注此任务",
      }),
    );
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("task")).toBe(
        overdueItem.item_id,
      ),
    );
    expect(
      screen.getByText(`本轮继续当前任务；下轮专注「${overdueItem.content}」`),
    ).toBeInTheDocument();
    const dropZone = screen
      .getByRole("heading", { name: "当前专注" })
      .closest("section")!;
    fireEvent.drop(dropZone, {
      dataTransfer: { getData: () => "unknown-item" },
    });
    expect(new URLSearchParams(window.location.search).get("task")).toBe(
      overdueItem.item_id,
    );
    fireEvent.drop(dropZone, {
      dataTransfer: { getData: () => planItem.item_id },
    });
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("task")).toBe(
        planItem.item_id,
      ),
    );
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(
        new URLSearchParams(window.location.search).get("inspector"),
      ).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "当前专注" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "暂停" })).toBeInTheDocument();
  });

  it("计划项与记录待办并列分组、标注来源，计划项可跳计划 Tab", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([todo])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json([overdueItem, planItem]),
      ),
    );

    render(<App />);

    await screen.findByRole("heading", { name: "待办事项" });
    const card = actionFlow();
    const recordList = await screen.findByRole("list", {
      name: "待处理记录列表",
    });
    expect(
      await within(recordList).findByRole("link", { name: /新录音 1/ }),
    ).toBeInTheDocument();
    // 双源分组标签。
    expect(within(card).getByText("学习计划")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待处理" })).toBeInTheDocument();

    const list = within(card).getByRole("list", {
      name: "今日待学计划项列表",
    });
    // 排期日即今天显示「今天」，早于今天显示月日＋逾期。
    const todayRow = within(list).getByText("通读 LCEL 转写笔记").closest("li");
    expect(todayRow).not.toBeNull();
    expect(
      within(todayRow as HTMLElement).getByText("今天"),
    ).toBeInTheDocument();
    expect(
      within(todayRow as HTMLElement).getByText("langchain学习"),
    ).toBeInTheDocument();
    expect(
      within(todayRow as HTMLElement).getByText("30 分钟"),
    ).toBeInTheDocument();
    const overdueRow = within(list).getByText("复习进程调度概念").closest("li");
    expect(overdueRow).not.toBeNull();
    expect(
      within(overdueRow as HTMLElement).getByText("逾期"),
    ).toBeInTheDocument();
    // 内容链接跳转该空间的计划 Tab（跨空间来源标注）。
    const link = within(todayRow as HTMLElement).getByRole("link", {
      name: "通读 LCEL 转写笔记",
    });
    expect(link).toHaveAttribute("href", `/spaces/${COURSE_ID}?tab=plan`);

    // 记录待办分组仍是去确认链接。
    expect(
      within(recordList).getByRole("link", { name: /新录音 1/ }),
    ).toHaveAttribute("href", `/records/${todo.record_id}`);
  });

  it("勾选完成直接作用于计划项（与计划 Tab 同一端点），统计当场刷新", async () => {
    let remaining = 1;
    let completeCalls = 0;
    let trendCalls = 0;
    let releaseCompletion = () => {};
    const completionGate = new Promise<void>((resolve) => {
      releaseCompletion = resolve;
    });
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json(remaining > 0 ? [planItem] : []),
      ),
      // 完成时间戳进入今日学习时长：失效 today 缓存后趋势须当场重拉（不等重进页面）。
      http.get(`${TEST_SIDECAR_URL}/api/today/stats/trend`, ({ request }) => {
        if (new URL(request.url).searchParams.get("days") === "30") {
          trendCalls += 1;
        }
        return HttpResponse.json([]);
      }),
      http.post(
        `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${planItem.plan_id}/items/item-1/complete`,
        async () => {
          completeCalls += 1;
          await completionGate;
          remaining = 0;
          return HttpResponse.json({ ...planItem, status: "DONE" });
        },
      ),
    );

    render(<App />);

    const checkbox = await screen.findByRole("checkbox", {
      name: "完成计划项「通读 LCEL 转写笔记」",
    });
    await waitFor(() => expect(trendCalls).toBeGreaterThan(0));
    const trendCallsBeforeComplete = trendCalls;
    fireEvent.click(checkbox);

    expect(await screen.findByText("正在完成")).toBeInTheDocument();
    expect(checkbox).toHaveAttribute("aria-disabled", "true");
    releaseCompletion();

    await waitFor(() => expect(completeCalls).toBe(1));
    // 完成后列表刷新，条目消失（区块随双源皆空撤下）。
    await waitFor(() =>
      expect(
        screen.queryByRole("checkbox", {
          name: "完成计划项「通读 LCEL 转写笔记」",
        }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(trendCalls).toBeGreaterThan(trendCallsBeforeComplete),
    );
  });

  it("双源皆空时不渲染区块", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () => HttpResponse.json([])),
    );

    render(<App />);

    await screen.findByRole("heading", { name: "学习趋势" });
    expect(
      screen.queryByRole("heading", { name: "等待确认的总结" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("学习计划")).not.toBeInTheDocument();
  });

  it("完成请求失败时复选框保持未勾选（与计划 Tab 同为受控，无假完成态）", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () => HttpResponse.json([planItem])),
      http.post(
        `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${planItem.plan_id}/items/item-1/complete`,
        () => HttpResponse.json({ detail: "sidecar 抖动" }, { status: 500 }),
      ),
    );

    render(<App />);

    const checkbox = await screen.findByRole("checkbox", {
      name: "完成计划项「通读 LCEL 转写笔记」",
    });
    fireEvent.click(checkbox);

    // 失败后：条目仍在列表（服务端仍 PENDING）、复选框保持未勾选——勾选态
    // 由数据受控（计划 Tab checked={done} 同构），非受控翻转会产生假完成。
    await waitFor(() => expect(checkbox).not.toBeChecked(), { timeout: 3_000 });
    expect(
      screen.getByRole("checkbox", {
        name: "完成计划项「通读 LCEL 转写笔记」",
      }),
    ).toBeInTheDocument();
    expect(
      within(actionFlow()).getByText("通读 LCEL 转写笔记"),
    ).toBeInTheDocument();
  });

  it("计划项读取失败显示行内错误与重试", async () => {
    let fail = true;
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () =>
        fail
          ? HttpResponse.json({ detail: "sidecar 抖动" }, { status: 500 })
          : HttpResponse.json([planItem]),
      ),
    );

    render(<App />);

    const alert = await screen.findByRole("alert", undefined, {
      timeout: 8_000,
    });
    expect(alert).toHaveTextContent("今日待办暂时无法读取");

    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("checkbox", {
        name: "完成计划项「通读 LCEL 转写笔记」",
      }),
    ).toBeInTheDocument();
  }, 20_000);
});
