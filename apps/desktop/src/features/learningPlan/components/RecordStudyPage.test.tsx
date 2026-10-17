// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "@/App";
import type { RecordStudy } from "@/features/learningPlan/api/study";
import { server } from "@/mocks/server";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";

const ITEM = "d0000000-0000-4000-8000-000000000001";
const RECORD = "a0000000-0000-4000-8000-000000000001";
const COURSE = "c0000000-0000-4000-8000-000000000001";
const PLAN = "70000000-0000-4000-8000-000000000001";
const GOAL = "90000000-0000-4000-8000-000000000001";
const BASE = `${TEST_SIDECAR_URL}/api/plan-items/${ITEM}/study`;
let state: RecordStudy;
let starts: number;
let savedTabs: string[];

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

beforeEach(() => {
  starts = 0;
  savedTabs = [];
  state = {
    item: {
      id: ITEM,
      action_type: "STUDY_RECORD",
      content: "学习 Redis 资料",
      record_id: null,
      phase_title: "基础",
      priority: 1,
      scheduled_date: "2026-10-17",
      status: "PENDING",
      user_locked: false,
    },
    course_id: COURSE,
    goal_id: GOAL,
    plan_id: PLAN,
    editable: true,
    source_status: "MISSING",
    source: null,
    sources: [{ record_id: RECORD, title: "Redis 核心资料", read_only: false }],
    sources_truncated: false,
    visit_id: null,
    started_at: null,
    tab: "summary",
    entry_path: `/plan-items/${ITEM}/study`,
  };
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE}`, () =>
      HttpResponse.json({
        id: COURSE,
        name: "Redis 学习",
        learning_context: "INTEREST",
        depth: "BEGINNER",
        status: "ACTIVE",
        hot_words: [],
        created_at: "2026-10-17T00:00:00Z",
        updated_at: "2026-10-17T00:00:00Z",
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE}/records`, () =>
      HttpResponse.json([]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE}/goals`, () =>
      HttpResponse.json([
        {
          id: GOAL,
          course_id: COURSE,
          goal_type: "SKILL",
          title: "掌握 Redis",
          status: "ACTIVE",
          scope_source: "USER_CONFIRMED",
          scope_confirmed: true,
        },
      ]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE}/plans`, () =>
      HttpResponse.json([
        {
          id: PLAN,
          goal_id: GOAL,
          course_id: COURSE,
          plan_version: 1,
          status: "ACTIVE",
          effective_from: "2026-10-17",
          item_count: 1,
        },
      ]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE}/plans/${PLAN}`, () =>
      HttpResponse.json({
        id: PLAN,
        goal_id: GOAL,
        course_id: COURSE,
        plan_version: 1,
        status: "ACTIVE",
        effective_from: "2026-10-17",
        items: [state.item],
      }),
    ),
    http.post(
      `${TEST_SIDECAR_URL}/api/courses/${COURSE}/plans/${PLAN}/items/${ITEM}/complete`,
      () => {
        state = {
          ...state,
          item: {
            ...state.item,
            status: "DONE",
            completed_at: "2026-10-17T08:00:00Z",
          },
        };
        return HttpResponse.json(state.item);
      },
    ),
    http.get(BASE, () => HttpResponse.json(state)),
    http.patch(
      `${TEST_SIDECAR_URL}/api/courses/${COURSE}/plans/${PLAN}/items/${ITEM}`,
      async ({ request }) => {
        const body = (await request.json()) as { record_id: string };
        state = {
          ...state,
          item: { ...state.item, record_id: body.record_id },
          source_status: "AVAILABLE",
          source: state.sources[0],
        };
        return HttpResponse.json(state.item);
      },
    ),
    http.post(`${BASE}/start`, async ({ request }) => {
      starts++;
      const body = (await request.json()) as { request_id: string };
      state = {
        ...state,
        visit_id: body.request_id,
        started_at: "2026-10-17T08:00:00Z",
      };
      return HttpResponse.json(state);
    }),
    http.put(`${BASE}/tab`, async ({ request }) => {
      const body = (await request.json()) as { tab: RecordStudy["tab"] };
      savedTabs.push(body.tab);
      state = { ...state, tab: body.tab };
      return HttpResponse.json(state);
    }),
    http.get(`${TEST_SIDECAR_URL}/api/records/${RECORD}`, () =>
      HttpResponse.json({
        id: RECORD,
        course_id: COURSE,
        capture_type: "PASTE",
        title: "Redis 核心资料",
        status: "SUMMARY_READY",
        duration_ms: 0,
        created_at: "2026-10-17T00:00:00Z",
        updated_at: "2026-10-17T00:00:00Z",
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${RECORD}/summary`, () =>
      HttpResponse.json({ action_required: "NONE", summary: null }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${RECORD}/transcript`, () =>
      HttpResponse.json({
        status: "READY",
        transcript: {
          id: "transcript",
          record_id: RECORD,
          content: "Redis 原始学习材料",
          language: "zh",
          source_version: 1,
          edited_by_user: false,
        },
      }),
    ),
    http.get(
      `${TEST_SIDECAR_URL}/api/records/${RECORD}/transcript/segments`,
      () => HttpResponse.json([]),
    ),
    http.get(
      `${TEST_SIDECAR_URL}/api/records/${RECORD}/document-segments`,
      () => HttpResponse.json({ items: [] }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${RECORD}/jobs`, () =>
      HttpResponse.json({ jobs: [], progress: 100 }),
    ),
  );
  window.history.replaceState(null, "", `/plan-items/${ITEM}/study`);
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

it("选择资料并确认后才关联，启动、页签、返回和再次打开均保留本项身份", async () => {
  render(<App />);
  expect(
    await screen.findByRole("button", { name: "确认关联此资料" }),
  ).toBeDisabled();
  expect(starts).toBe(0);
  fireEvent.click(screen.getByRole("radio", { name: "Redis 核心资料" }));
  fireEvent.click(screen.getByRole("button", { name: "确认关联此资料" }));
  const start = await screen.findByRole("button", { name: "开始学习资料" });
  await waitFor(() => expect(start).toHaveFocus());
  expect(state.item.record_id).toBe(RECORD);
  expect(starts).toBe(0);
  fireEvent.click(start);
  const back = await screen.findByRole("link", { name: "返回原计划项" });
  expect(back).toHaveAttribute("href", `/plan-items/${ITEM}/study`);
  expect(starts).toBe(1);
  fireEvent.click(screen.getByRole("tab", { name: "Transcript" }));
  await waitFor(() => expect(savedTabs).toEqual(["transcript"]));
  await waitFor(() =>
    expect(window.location.search).toContain("tab=transcript"),
  );
  fireEvent.click(back);
  const resume = await screen.findByRole("button", { name: "继续学习资料" });
  expect(screen.getByRole("link", { name: "返回学习计划" })).toHaveAttribute(
    "href",
    `/spaces/${COURSE}?tab=plan&planItem=${ITEM}`,
  );
  fireEvent.click(resume);
  await screen.findByRole("link", { name: "返回原计划项" });
  expect(window.location.search).toContain("tab=transcript");
  expect(starts).toBe(2);
  fireEvent.click(await screen.findByRole("link", { name: "返回原计划项" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "我确认此计划项已完成" }),
  );
  await screen.findByText("计划项已完成，可继续学习巩固。");
  fireEvent.click(screen.getByRole("link", { name: "返回学习计划" }));
  const completed = await screen.findByRole("checkbox", {
    name: /完成.*学习 Redis 资料/,
  });
  expect(completed).toBeChecked();
  await waitFor(() => expect(completed.closest("li")).toHaveFocus());
});

it("失效来源和只读历史无启动入口，保留重新关联或历史结果说明", async () => {
  state.source_status = "UNAVAILABLE";
  render(<App />);
  await screen.findByText(
    "原资料已删除、移出课程或共享引用已失效，请重新关联。",
  );
  expect(
    screen.queryByRole("button", { name: "开始学习资料" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Redis 核心资料" }),
  ).not.toBeInTheDocument();
  cleanup();
  state.editable = false;
  render(<App />);
  await screen.findByText("历史计划、完结目标及已跳过项仅可查看既有学习记录。");
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "我确认此计划项已完成" }),
  ).not.toBeInTheDocument();
});

it("访问身份不匹配时不给记录内容或写入本项页签", async () => {
  state.visit_id = "current-visit";
  state.source = state.sources[0];
  state.source_status = "AVAILABLE";
  window.history.replaceState(
    null,
    "",
    `/records/${RECORD}?studyItem=${ITEM}&studyVisit=old-visit&tab=transcript`,
  );
  render(<App />);
  await screen.findByText(
    "本次访问已失效，或计划及来源已变化，请返回原计划项查看并重新启动。",
  );
  expect(savedTabs).toEqual([]);
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
});

it("共享记录保持只读，页签仍可切换并返回原计划项", async () => {
  state.visit_id = "current-visit";
  state.source = { ...state.sources[0], read_only: true };
  state.source_status = "AVAILABLE";
  window.history.replaceState(
    null,
    "",
    `/records/${RECORD}?studyItem=${ITEM}&studyVisit=current-visit&tab=transcript`,
  );
  render(<App />);
  await screen.findByText("Redis 原始学习材料");
  expect(screen.getByRole("button", { name: "编辑正文" })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "删除学习记录" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Summary" })).toBeEnabled();
  expect(screen.getByRole("link", { name: "返回原计划项" })).toHaveAttribute(
    "href",
    `/plan-items/${ITEM}/study`,
  );
});
