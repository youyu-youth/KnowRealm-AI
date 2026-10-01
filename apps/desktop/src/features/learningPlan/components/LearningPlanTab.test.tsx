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
const GOAL2_ID = "55555555-5555-4555-8555-555555555555";
const PLAN2_ID = "66666666-6666-4666-8666-666666666666";

const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const GOALS_URL = `${DETAIL_URL}/goals`;
const VERSIONS_URL = `${DETAIL_URL}/plans?goal_id=${GOAL_ID}`;
const VERSIONS2_URL = `${DETAIL_URL}/plans?goal_id=${GOAL2_ID}`;
const PLAN_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${PLAN_ID}`;
const HISTORY_PLAN_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${HISTORY_PLAN_ID}`;
const PLAN2_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}/plans/${PLAN2_ID}`;
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

const completedGoal: GoalOut = {
  ...activeGoal,
  id: GOAL2_ID,
  title: "吃透 Linux 内核",
  status: "COMPLETED",
  updated_at: "2026-09-25T00:00:00.000000Z",
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

const completedGoalVersions: PlanVersionOut[] = [
  {
    id: PLAN2_ID,
    goal_id: GOAL2_ID,
    course_id: COURSE_ID,
    plan_version: 1,
    status: "ACTIVE",
    effective_from: "2026-09-05",
    effective_to: null,
    item_count: 1,
  },
];

const completedGoalPlan: PlanOut = {
  id: PLAN2_ID,
  goal_id: GOAL2_ID,
  course_id: COURSE_ID,
  plan_version: 1,
  status: "ACTIVE",
  effective_from: "2026-09-05",
  effective_to: null,
  items: [itemOf("done-1", { content: "读完内核调度器章节", priority: 1 })],
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

  it("目标完结后保留只读查看入口与设定新目标引导", async () => {
    server.use(
      http.get(GOALS_URL, () => HttpResponse.json([completedGoal])),
      http.get(VERSIONS2_URL, () => HttpResponse.json(completedGoalVersions)),
      http.get(PLAN2_URL, () => HttpResponse.json(completedGoalPlan)),
    );

    renderAt(ROUTE_PATH);

    // 回落到最近历史目标只读展示，计划项仍可追溯（spec 用户故事 16）。
    expect(
      await screen.findByText("读完内核调度器章节", undefined, {
        timeout: 5_000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("吃透 Linux 内核")).toBeInTheDocument();
    expect(screen.getByText("已完结")).toBeInTheDocument();
    // 执行面整体只读：无编辑/跳过，勾选禁用（aria-disabled——Base UI 复选框
    // 渲染 span，B1 Switch 同坑）。
    expect(
      screen.queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "跳过" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "完成「读完内核调度器章节」" }),
    ).toHaveAttribute("aria-disabled", "true");
    // 无进行中目标 → 设定新目标引导并排保留。
    expect(screen.getByText("还没有进行中的学习目标")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "去对话设定目标" }),
    ).toHaveAttribute("href", "/chat");
  });

  it("多目标时切换选择器查看历史目标（默认跟随进行中）", async () => {
    // MSW 对带 query 的 path 只按 pathname 匹配（query 不构成区分条件）：
    // 两个目标的版本列表必须由同一 handler 按 goal_id 分流，否则切换后的
    // 请求会被先注册的同路径 handler 劫走。
    server.use(
      http.get(GOALS_URL, () => HttpResponse.json([activeGoal, completedGoal])),
      http.get(`${DETAIL_URL}/plans`, ({ request }) => {
        const goalId = new URL(request.url).searchParams.get("goal_id");
        return HttpResponse.json(
          goalId === GOAL2_ID ? completedGoalVersions : versions,
        );
      }),
      http.get(PLAN_URL, () => HttpResponse.json(currentPlan)),
      http.get(PLAN2_URL, () => HttpResponse.json(completedGoalPlan)),
    );

    renderAt(ROUTE_PATH);

    // 默认跟随进行中目标（日常执行面不变）。
    expect(
      await screen.findByText("通读进程调度转写", undefined, {
        timeout: 5_000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("掌握操作系统的核心概念")).toBeInTheDocument();

    // 切换目标后 GoalWorkspace 按 key 重挂载（版本状态重置），trigger 节点
    // 随之替换：不能沿用 selectOption 的旧引用断言，以视图内容切换为断言。
    const goalTrigger = screen.getByRole("combobox", { name: "切换学习目标" });
    await waitFor(() => expect(goalTrigger).toBeEnabled());
    fireEvent.click(goalTrigger);
    const historyOption = await screen.findByRole("option", {
      name: "吃透 Linux 内核 · 历史",
    });
    fireEvent.pointerDown(historyOption);
    fireEvent.pointerUp(historyOption);
    fireEvent.click(historyOption);

    // 先确认目标卡切到历史目标（区分「未切换」与「计划详情未渲染」）。
    expect(
      await screen.findByText("吃透 Linux 内核", undefined, {
        timeout: 5_000,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("读完内核调度器章节", undefined, {
        timeout: 5_000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("已完结")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
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
    // 未改任何字段时保存禁用（不发会被后端拒绝的空载荷）。
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
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
