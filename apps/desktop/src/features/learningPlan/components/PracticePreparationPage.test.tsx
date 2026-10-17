// @vitest-environment jsdom

import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "@/App";
import { server } from "@/mocks/server";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import type {
  PracticeState,
  RequirementsUpdate,
} from "@/features/learningPlan/api/practice";

const ITEM = "d0000000-0000-4000-8000-000000000001";
const BASE = `${TEST_SIDECAR_URL}/api/plan-items/${ITEM}/practice`;
const source = {
  record_id: "a0000000-0000-4000-8000-000000000001",
  title: "Redis 核心资料",
  eligible_count: 8,
  related_count: 8,
  version: "source-version-1",
};
const second = {
  ...source,
  record_id: "a0000000-0000-4000-8000-000000000002",
  title: "Redis 补充资料",
  eligible_count: 7,
  related_count: 7,
  version: "source-version-2",
};
let state: PracticeState;
let confirmed: RequirementsUpdate | null;

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

beforeEach(() => {
  state = {
    item_id: ITEM,
    course_id: "c0000000-0000-4000-8000-000000000001",
    plan_id: "70000000-0000-4000-8000-000000000001",
    plan_content: "做 15 道 Redis 基础题",
    editable: true,
    requirements_stale: false,
    requirements: null,
    sources: [source, second],
    preparations: [],
  };
  confirmed = null;
  server.use(
    http.get(BASE, () => HttpResponse.json(state)),
    http.put(`${BASE}/requirements`, async ({ request }) => {
      confirmed = (await request.json()) as RequirementsUpdate;
      state = {
        ...state,
        requirements: {
          ...confirmed,
          id: "requirement",
          revision: confirmed.expected_revision + 1,
          confirmed_at: "2026-10-17T00:00:00Z",
        },
      };
      return HttpResponse.json(state.requirements);
    }),
  );
  window.history.replaceState(null, "", `/plan-items/${ITEM}/practice`);
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function savedRequirements() {
  state.requirements = {
    id: "requirements",
    revision: 1,
    plan_content: state.plan_content,
    topic: "Redis 基础",
    question_count: 15,
    question_types: ["SHORT_ANSWER"],
    record_ids: [source.record_id],
    source_versions: { [source.record_id]: source.version },
    confirmed_at: "2026-10-17T00:00:00Z",
  };
}

it("首次合并确认要求，未明确数量前不能准备，不修改计划正文", async () => {
  render(<App />);
  const count = await screen.findByRole("spinbutton", { name: "精确题量" });
  expect(count).toHaveValue(null);
  expect(screen.getByRole("button", { name: "确认并保存要求" })).toBeDisabled();
  fireEvent.change(count, { target: { value: "15" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /Redis 核心资料/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认并保存要求" }));
  await screen.findByRole("button", { name: "准备题集" });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "准备题集" })).toHaveFocus(),
  );
  expect(confirmed).toMatchObject({
    question_count: 15,
    record_ids: [source.record_id],
    plan_content: "做 15 道 Redis 基础题",
    source_versions: { [source.record_id]: source.version },
  });
  expect(screen.getByRole("link", { name: "返回学习计划" })).toHaveAttribute(
    "href",
    `/spaces/${state.course_id}?tab=plan`,
  );
});

it("缺题建议不自动扩源，用户选择并确认后保存新的修订", async () => {
  savedRequirements();
  state.preparations = [
    {
      id: "prep",
      item_id: ITEM,
      entry_path: `/plan-items/${ITEM}/practice`,
      job_id: "job",
      requirements_revision: 1,
      status: "SUCCEEDED",
      outcome: "INSUFFICIENT",
      target_count: 15,
      eligible_count: 8,
      related_count: 8,
      selected_count: 0,
      examined_count: 15,
      total_candidates: 15,
      course_scan_complete: true,
      error_code: null,
      sources: [{ ...source, matching_basis: ["TOPIC_CONCEPT"] }],
      suggestions: [{ ...second, matching_basis: ["TOPIC_APPLICATION"] }],
    },
  ];
  render(<App />);
  await screen.findByText("确认范围内只有 8 道相关题，目标为 15 题");
  expect(screen.getByText("· 考查主题核心概念")).toBeInTheDocument();
  expect(screen.getByText("· 应用主题知识")).toBeInTheDocument();
  expect(confirmed).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "修改要求 / 确认扩源" }));
  expect(
    screen.getByRole("checkbox", { name: /Redis 核心资料/ }),
  ).toBeChecked();
  expect(
    screen.getByRole("checkbox", { name: /Redis 补充资料/ }),
  ).not.toBeChecked();
  fireEvent.click(screen.getByRole("checkbox", { name: /Redis 补充资料/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认并保存要求" }));
  await screen.findByText("要求修订 2");
  expect(confirmed).toMatchObject({
    expected_revision: 1,
    question_count: 15,
    record_ids: [source.record_id, second.record_id],
    source_versions: {
      [source.record_id]: source.version,
      [second.record_id]: second.version,
    },
  });
});

it("准备请求网络失败后保留请求身份，离开页面不取消已受理任务", async () => {
  savedRequirements();
  const requests: string[] = [];
  server.use(
    http.post(`${BASE}/preparations`, async ({ request }) => {
      const body = (await request.json()) as { request_id: string };
      requests.push(body.request_id);
      if (requests.length === 1) return HttpResponse.error();
      state.preparations = [
        {
          id: "prep",
          item_id: ITEM,
          entry_path: `/plan-items/${ITEM}/practice`,
          job_id: "job",
          requirements_revision: 1,
          status: "RUNNING",
          outcome: null,
          target_count: 15,
          eligible_count: 0,
          related_count: 0,
          selected_count: 0,
          examined_count: 0,
          total_candidates: 0,
          course_scan_complete: false,
          error_code: null,
          sources: [],
          suggestions: [],
        },
      ];
      return HttpResponse.json(state.preparations[0], { status: 202 });
    }),
  );
  const first = render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "准备题集" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "准备题集" }));
  await screen.findByText("正在匹配真实习题");
  expect(requests[0]).toBe(requests[1]);
  first.unmount();
  render(<App />);
  await screen.findByText("正在匹配真实习题");
  let cancelCalls = 0;
  server.use(
    http.post(`${BASE}/preparations/prep/cancel`, () => {
      cancelCalls++;
      state.preparations[0].status = "CANCELLED";
      return HttpResponse.json(state.preparations[0]);
    }),
  );
  expect(cancelCalls).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "取消本次匹配" }));
  await waitFor(() =>
    expect(screen.getByText("本次匹配已取消")).toBeInTheDocument(),
  );
  expect(cancelCalls).toBe(1);
});

it("刷新来源版本保留编辑输入，并由用户显式重新读取确认基线", async () => {
  render(<App />);
  const count = await screen.findByRole("spinbutton", { name: "精确题量" });
  fireEvent.change(count, { target: { value: "15" } });
  fireEvent.change(screen.getByRole("textbox", { name: "练习主题" }), {
    target: { value: "Redis 持久化" },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: /Redis 核心资料/ }));
  state = {
    ...state,
    sources: [{ ...source, version: "new-version" }, second],
  };
  fireEvent.click(screen.getByRole("button", { name: "刷新状态" }));
  await waitFor(() => expect(count).toHaveValue(15));
  expect(screen.getByRole("textbox", { name: "练习主题" })).toHaveValue(
    "Redis 持久化",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "重新读取来源并核对（保留输入）" }),
  );
  await screen.findByText("来源已重新读取，未保存输入已保留，请核对后确认");
  fireEvent.click(screen.getByRole("button", { name: "确认并保存要求" }));
  await screen.findByRole("button", { name: "准备题集" });
  expect(confirmed).toMatchObject({
    topic: "Redis 持久化",
    question_count: 15,
    source_versions: { [source.record_id]: "new-version" },
  });
});

it("来源失效后仍可取消旧选择并确认有效来源", async () => {
  savedRequirements();
  state.sources = [second];
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "修改要求 / 确认扩源" }),
  );
  fireEvent.click(screen.getByRole("checkbox", { name: /来源已失效/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Redis 补充资料/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认并保存要求" }));
  await screen.findByText("要求修订 2");
  expect(confirmed).toMatchObject({
    record_ids: [second.record_id],
    source_versions: { [second.record_id]: second.version },
  });
});
