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
import { afterEach, describe, expect, it, vi } from "vitest";
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
  return date.toISOString().slice(0, 10);
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

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

// 双源清单渲染在行动流内，学习链复用同一真实查询。
function actionFlow(): HTMLElement {
  const heading = screen.getByText("行动流");
  const card = heading.closest("section");
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

describe("今日待学双源清单", () => {
  it("计划项与记录待办并列分组、标注来源，计划项可跳计划 Tab", async () => {
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([todo])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json([overdueItem, planItem]),
      ),
    );

    render(<App />);

    await screen.findByText("行动流");
    const card = actionFlow();
    expect(
      await within(card).findByRole("heading", { name: "等待确认的总结" }),
    ).toBeInTheDocument();
    // 双源分组标签。
    expect(within(card).getByText("学习计划")).toBeInTheDocument();
    expect(within(card).getByText("记录待办")).toBeInTheDocument();

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
    const recordList = within(card).getByRole("list", {
      name: "待确认总结列表",
    });
    expect(
      within(recordList).getByRole("link", { name: /新录音 1/ }),
    ).toHaveAttribute("href", `/records/${todo.record_id}`);
  });

  it("勾选完成直接作用于计划项（与计划 Tab 同一端点）", async () => {
    let remaining = 1;
    let completeCalls = 0;
    server.use(
      http.get(PENDING_URL, () => HttpResponse.json([])),
      http.get(PLAN_ITEMS_URL, () =>
        HttpResponse.json(remaining > 0 ? [planItem] : []),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${planItem.plan_id}/items/item-1/complete`,
        () => {
          completeCalls += 1;
          remaining = 0;
          return HttpResponse.json({ ...planItem, status: "DONE" });
        },
      ),
    );

    render(<App />);

    const checkbox = await screen.findByRole("checkbox", {
      name: "完成计划项「通读 LCEL 转写笔记」",
    });
    fireEvent.click(checkbox);

    await waitFor(() => expect(completeCalls).toBe(1));
    // 完成后列表刷新，条目消失（区块随双源皆空撤下）。
    await waitFor(() =>
      expect(
        screen.queryByRole("checkbox", {
          name: "完成计划项「通读 LCEL 转写笔记」",
        }),
      ).not.toBeInTheDocument(),
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
