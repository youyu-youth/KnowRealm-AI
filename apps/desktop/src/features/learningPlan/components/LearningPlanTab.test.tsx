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

type CourseDetail = components["schemas"]["CourseDetailOut"];
type GoalOut = components["schemas"]["GoalOut"];
type PlanVersionOut = components["schemas"]["PlanVersionOut"];
type PlanOut = components["schemas"]["PlanOut"];
type PlanItemUpdateBody = components["schemas"]["PlanItemUpdate"];
type PlanItemOut = components["schemas"]["PlanItemOut"];

const COURSE_ID = "22222222-2222-4222-8222-222222222222";
const GOAL_ID = "11111111-1111-4111-8111-111111111111";
const PLAN_ID = "33333333-3333-4333-8333-333333333333";
const HISTORY_PLAN_ID = "44444444-4444-4444-8444-444444444444";

const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const GOALS_URL = `${DETAIL_URL}/goals`;
const VERSIONS_URL = `${DETAIL_URL}/plans?goal_id=${GOAL_ID}`;
const PLAN_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${PLAN_ID}`;
const HISTORY_PLAN_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${HISTORY_PLAN_ID}`;
const ITEM1_URL = `${PLAN_URL}/items/item-1`;
const ROUTE_PATH = `/spaces/${COURSE_ID}?tab=plan`;

const schoolCourse: CourseDetail = {
  id: COURSE_ID,
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: "理解进程、内存与文件系统。",
  status: "ACTIVE",
  hot_words: [],
  created_at: "2026-08-17T00:00:00.000000Z",
  updated_at: "2026-08-18T00:00:00.000000Z",
};

const activeGoal: GoalOut = {
  id: GOAL_ID,
  course_id: COURSE_ID,
  goal_type: "SKILL",
  title: "掌握操作系统的核心概念",
  target_date: "2026-10-31",
  daily_minutes: 60,
  target_score: null,
  scope_source: "USER_CONFIRMED",
  scope_confirmed: true,
  status: "ACTIVE",
  created_at: "2026-09-01T00:00:00.000000Z",
  updated_at: "2026-09-01T00:00:00.000000Z",
};

const versions: PlanVersionOut[] = [
  {
    id: PLAN_ID,
    goal_id: GOAL_ID,
    course_id: COURSE_ID,
    plan_version: 2,
    status: "ACTIVE",
    effective_from: "2026-09-20",
    effective_to: null,
    item_count: 3,
  },
  {
    id: HISTORY_PLAN_ID,
    goal_id: GOAL_ID,
    course_id: COURSE_ID,
    plan_version: 1,
    status: "SUPERSEDED",
    effective_from: "2026-09-10",
    effective_to: "2026-09-20",
    item_count: 2,
  },
];

function itemOf(id: string, overrides: Partial<PlanItemOut> = {}): PlanItemOut {
  return {
    id,
    action_type: "STUDY_RECORD",
    content: `条目-${id}`,
    record_id: null,
    concept_id: null,
    phase_title: "起步",
    priority: 1,
    estimated_minutes: 30,
    scheduled_date: "2026-09-30",
    status: "PENDING",
    user_locked: false,
    completed_at: null,
    reason: null,
    ...overrides,
  };
}

const currentItems: PlanItemOut[] = [
  itemOf("item-1", { content: "通读进程调度转写", priority: 1 }),
  itemOf("item-2", {
    content: "整理进程知识点",
    priority: 2,
    status: "DONE",
    completed_at: "2026-09-29T10:00:00.000000Z",
    user_locked: true,
  }),
  itemOf("item-3", {
    content: "完成调度习题",
    action_type: "PRACTICE_QUIZ",
    phase_title: "巩固",
    priority: 3,
    estimated_minutes: 50,
  }),
];

const currentPlan: PlanOut = {
  id: PLAN_ID,
  goal_id: GOAL_ID,
  course_id: COURSE_ID,
  plan_version: 2,
  status: "ACTIVE",
  effective_from: "2026-09-20",
  effective_to: null,
  items: currentItems,
};

const historyPlan: PlanOut = {
  id: HISTORY_PLAN_ID,
  goal_id: GOAL_ID,
  course_id: COURSE_ID,
  plan_version: 1,
  status: "SUPERSEDED",
  effective_from: "2026-09-10",
  effective_to: "2026-09-20",
  items: [
    itemOf("h-1", { content: "旧版条目一", priority: 1 }),
    itemOf("h-2", { content: "旧版条目二", priority: 2 }),
  ],
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  server.use(
    http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    http.get(`${DETAIL_URL}/records`, () => HttpResponse.json([])),
    http.get(GOALS_URL, () => HttpResponse.json([activeGoal])),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

async function selectOption(comboboxName: string, optionName: string) {
  const trigger = screen.getByRole("combobox", { name: comboboxName });
  await waitFor(() => expect(trigger).toBeEnabled());
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe("学习计划 Tab", () => {
  it("渲染目标卡与阶段分组计划项（tab 入 URL 路由可达）", async () => {
    server.use(
      http.get(VERSIONS_URL, () => HttpResponse.json(versions)),
      http.get(PLAN_URL, () => HttpResponse.json(currentPlan)),
    );

    renderAt(ROUTE_PATH);

    // 计划项加载完成后再断言目标卡进度与行细节（目标卡先于计划详情渲染）。
    expect(
      await screen.findByText("通读进程调度转写", undefined, {
        timeout: 5_000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("掌握操作系统的核心概念")).toBeInTheDocument();
    expect(screen.getByText("技能")).toBeInTheDocument();
    expect(screen.getByText("1/3 项")).toBeInTheDocument();
    // 阶段分组标题与项。
    expect(screen.getByRole("heading", { name: "起步" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "巩固" })).toBeInTheDocument();
    expect(screen.getByText("通读进程调度转写")).toBeInTheDocument();
    expect(screen.getByText("完成调度习题")).toBeInTheDocument();
    // 已完成行：勾选态 + 已完成标记 + 不再提供编辑/跳过（Base UI 复选框渲染
    // span，禁用态断言走 aria-disabled——B1 Switch 同坑）。
    const doneBox = screen.getByRole("checkbox", {
      name: "完成「整理进程知识点」",
    });
    expect(doneBox).toBeChecked();
    expect(doneBox).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("已完成")).toBeInTheDocument();
    // 待执行行提供编辑与跳过。
    const pendingRow = screen.getByText("通读进程调度转写").closest("li");
    expect(pendingRow).not.toBeNull();
    expect(
      within(pendingRow as HTMLElement).getByRole("button", { name: "编辑" }),
    ).toBeInTheDocument();
    expect(
      within(pendingRow as HTMLElement).getByRole("button", { name: "跳过" }),
    ).toBeInTheDocument();
  });

  it("勾选完成调用计划项完成端点并刷新状态", async () => {
    let completeCalls = 0;
    let item1Done = false;
    server.use(
      http.get(VERSIONS_URL, () => HttpResponse.json(versions)),
      http.get(PLAN_URL, () =>
        HttpResponse.json({
          ...currentPlan,
          items: currentItems.map((item) =>
            item.id === "item-1" && item1Done
              ? {
                  ...item,
                  status: "DONE",
                  completed_at: "2026-09-30T10:00:00.000000Z",
                }
              : item,
          ),
        }),
      ),
      http.post(`${ITEM1_URL}/complete`, () => {
        completeCalls += 1;
        item1Done = true;
        return HttpResponse.json({
          ...currentItems[0],
          status: "DONE",
          completed_at: "2026-09-30T10:00:00.000000Z",
        });
      }),
    );

    renderAt(ROUTE_PATH);

    const checkbox = await screen.findByRole("checkbox", {
      name: "完成「通读进程调度转写」",
    });
    fireEvent.click(checkbox);

    await waitFor(() => expect(completeCalls).toBe(1));
    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: "完成「通读进程调度转写」" }),
      ).toBeChecked(),
    );
  });

  it("无进行中目标时展示空态引导对话主路径", async () => {
    server.use(http.get(GOALS_URL, () => HttpResponse.json([])));

    renderAt(ROUTE_PATH);

    expect(
      await screen.findByText("还没有进行中的学习目标"),
    ).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "去对话设定目标" });
    expect(cta).toHaveAttribute("href", "/chat");
  });

  it("有目标无计划时引导生成计划草案", async () => {
    server.use(http.get(VERSIONS_URL, () => HttpResponse.json([])));

    renderAt(ROUTE_PATH);

    expect(await screen.findByText("还没有学习计划")).toBeInTheDocument();
    expect(screen.getByText("掌握操作系统的核心概念")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "去对话生成计划" }),
    ).toHaveAttribute("href", "/chat");
  });

  it("切换历史版本只读查看（无编辑/跳过、勾选禁用）", async () => {
    server.use(
      http.get(VERSIONS_URL, () => HttpResponse.json(versions)),
      http.get(PLAN_URL, () => HttpResponse.json(currentPlan)),
      http.get(HISTORY_PLAN_URL, () => HttpResponse.json(historyPlan)),
    );

    renderAt(ROUTE_PATH);
    await screen.findByText("通读进程调度转写", undefined, { timeout: 5_000 });

    await selectOption("切换计划版本", "第 1 版 · 历史");

    expect(await screen.findByText("历史版本 · 只读")).toBeInTheDocument();
    await screen.findByText("旧版条目一");
    expect(
      screen.queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "跳过" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "完成「旧版条目一」" }),
    ).toHaveAttribute("aria-disabled", "true");
  });

  it("内联编辑仅提交变更字段并保存回显", async () => {
    const patchBodies: object[] = [];
    server.use(
      http.get(VERSIONS_URL, () => HttpResponse.json(versions)),
      http.get(PLAN_URL, () =>
        HttpResponse.json({
          ...currentPlan,
          items: currentItems.map((item) =>
            item.id === "item-1" && patchBodies.length > 0
              ? { ...item, ...patchBodies[patchBodies.length - 1] }
              : item,
          ),
        }),
      ),
      http.patch(ITEM1_URL, async ({ request }) => {
        const body = (await request.json()) as PlanItemUpdateBody;
        patchBodies.push(body);
        return HttpResponse.json({
          ...currentItems[0],
          ...body,
        });
      }),
    );

    renderAt(ROUTE_PATH);

    const row = (
      await screen.findByText("通读进程调度转写", undefined, { timeout: 5_000 })
    ).closest("li");
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "编辑" }),
    );
    const minutes = await screen.findByRole("spinbutton", {
      name: "预估分钟数",
    });
    fireEvent.change(minutes, { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(patchBodies).toEqual([{ estimated_minutes: 45 }]),
    );
    // 保存成功后编辑行收起、新时长回显。
    await waitFor(() =>
      expect(
        screen.queryByRole("spinbutton", { name: "预估分钟数" }),
      ).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("45 分钟")).toBeInTheDocument();
  });
});
