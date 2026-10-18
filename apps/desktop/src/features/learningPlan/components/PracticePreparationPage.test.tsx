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
      reused_count: 0,
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
          reused_count: 0,
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

function readyPreparation() {
  state.preparations = [
    {
      id: "prep",
      item_id: ITEM,
      entry_path: `/plan-items/${ITEM}/practice`,
      job_id: "job",
      requirements_revision: 1,
      status: "SUCCEEDED",
      outcome: "READY",
      target_count: 15,
      eligible_count: 15,
      related_count: 15,
      selected_count: 15,
      examined_count: 16,
      total_candidates: 16,
      course_scan_complete: true,
      error_code: null,
      sources: [{ ...source, matching_basis: ["TOPIC_CONCEPT"] }],
      suggestions: [],
      reused_count: 0,
    },
  ];
}

const round = {
  version: "round-version-1",
  reused_count: 0,
  retry_available: false,
  test_id: "t0000000-0000-4000-8000-000000000001",
  round_no: 1,
  requirements_revision: 1,
  status: "IN_PROGRESS",
  entry_path: `/plan-items/${ITEM}/practice`,
  paper_path: `/spaces/${"c0000000-0000-4000-8000-000000000001"}/tests/t0000000-0000-4000-8000-000000000001`,
  total_count: 15,
  answered_count: 6,
  graded_count: 0,
  unscored_count: 0,
  score: null,
  score_denominator: null,
  grading_complete: false,
  started_at: "2026-10-17T00:00:00Z",
  completed_at: null,
  sources: [
    { record_id: source.record_id, title: "Redis 核心资料", valid: true },
  ],
};

it("题集就绪后开始练习进入同一轮，重试保留请求身份", async () => {
  savedRequirements();
  readyPreparation();
  const requests: string[] = [];
  server.use(
    http.post(`${BASE}/rounds`, async ({ request }) => {
      const body = (await request.json()) as { request_id: string };
      requests.push(body.request_id);
      if (requests.length === 1) return HttpResponse.error();
      state = { ...state, round: { ...round } };
      return HttpResponse.json(state.round);
    }),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "开始练习" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "开始练习" }));
  await screen.findByText("第 1 轮练习 · 进行中");
  expect(requests[0]).toBe(requests[1]);
  expect(screen.getByText("已答 6 / 15 题，已评分 0 题")).toBeInTheDocument();
  const link = screen.getByRole("link", { name: "继续本轮练习" });
  expect(link).toHaveAttribute(
    "href",
    "/spaces/c0000000-0000-4000-8000-000000000001/tests/t0000000-0000-4000-8000-000000000001?view=single",
  );
});

it("评分中的轮次展示部分成绩与实际分母，不提供开始入口", async () => {
  savedRequirements();
  state = {
    ...state,
    round: {
      ...round,
      status: "GRADING_FAILED",
      answered_count: 15,
      graded_count: 9,
      unscored_count: 6,
      score: 0.5,
      score_denominator: 9,
      grading_complete: true,
    },
  };
  render(<App />);
  await screen.findByText("第 1 轮练习 · 评分未完成，可重试未评分题");
  expect(screen.getByText("已答 15 / 15 题，已评分 9 题")).toBeInTheDocument();
  expect(screen.getByText("成绩 50%（实际评分分母 9 题）")).toBeInTheDocument();
  expect(
    screen.getByText("6 题尚未评分，成绩暂为部分成绩"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "开始练习" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "查看本轮结果" }),
  ).toBeInTheDocument();
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

it("已完成但仅评分13题时显示部分分母，失败重试沿用身份并刷新结果", async () => {
  savedRequirements();
  state.round = {
    ...round,
    status: "COMPLETED",
    answered_count: 15,
    graded_count: 13,
    unscored_count: 2,
    score: 0.5,
    score_denominator: 13,
    retry_available: true,
    grading_errors: { "14": "LLM_OUTPUT_INVALID" },
  };
  const requests: string[] = [];
  server.use(
    http.post(
      `${BASE}/rounds/${round.test_id}/retries`,
      async ({ request }) => {
        const body = (await request.json()) as { request_id: string };
        requests.push(body.request_id);
        if (requests.length === 1)
          return HttpResponse.json(
            {
              code: "LLM_PROVIDER_UNCONFIGURED",
              detail: "Provider unavailable",
            },
            { status: 409 },
          );
        state.round = {
          ...round,
          status: "COMPLETED",
          answered_count: 15,
          score: 0.5,
          graded_count: 15,
          unscored_count: 0,
          grading_complete: true,
          retry_available: false,
          grading_errors: {},
          score_denominator: 15,
        };
        return HttpResponse.json(state.round);
      },
    ),
  );
  render(<App />);
  await screen.findByText("成绩 50%（实际评分分母 13 题）");
  expect(
    screen.getByText("2 题尚未评分，成绩暂为部分成绩"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重试未评分题" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "请先配置（包含密钥的）LLM Provider",
  );
  fireEvent.click(screen.getByRole("button", { name: "重试未评分题" }));
  await screen.findByText("成绩 50%（实际评分分母 15 题）");
  expect(requests[0]).toBe(requests[1]);
  expect(
    screen.queryByRole("button", { name: "重试未评分题" }),
  ).not.toBeInTheDocument();
});

it("6/15重练须先确认放弃影响，取消无请求，准备后仍能继续旧轮", async () => {
  savedRequirements();
  state.round = { ...round };
  const bodies: unknown[] = [];
  server.use(
    http.post(`${BASE}/preparations`, async ({ request }) => {
      bodies.push(await request.json());
      readyPreparation();
      state.preparations[0].expected_round_id = round.test_id;
      state.preparations[0].reused_count = 15;
      return HttpResponse.json(state.preparations[0], { status: 202 });
    }),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "重新练习" }));
  await screen.findByRole("dialog");
  expect(screen.getByText(/旧轮已答 6 \/ 15 题/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保留当前轮" }));
  expect(bodies).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "重新练习" }));
  fireEvent.click(screen.getByRole("button", { name: "确认并准备新轮" }));
  await screen.findByRole("button", { name: "开始新一轮练习" });
  expect(bodies).toEqual([
    expect.objectContaining({
      expected_round_id: round.test_id,
      expected_round_version: "round-version-1",
      abandon_confirmed: true,
    }),
  ]);
  expect(
    screen.getByRole("link", { name: "继续本轮练习" }),
  ).toBeInTheDocument();
});

it("历史轮次通过URL切换，默认选择最近启动轮而非较高分旧轮", async () => {
  savedRequirements();
  readyPreparation();
  const latest = { ...round, test_id: "t2", round_no: 2, answered_count: 0 };
  const old = {
    ...round,
    status: "COMPLETED",
    answered_count: 15,
    graded_count: 15,
    score: 0.9,
    score_denominator: 15,
    grading_complete: true,
  };
  state.round = latest;
  state.rounds = [latest, old];
  state.preparations[0].expected_round_id = latest.test_id;
  server.use(
    http.post(`${BASE}/rounds`, () => {
      const next = { ...latest, test_id: "t3", round_no: 3 };
      state = {
        ...state,
        round: next,
        rounds: [next, ...(state.rounds ?? [])],
      };
      return HttpResponse.json(next);
    }),
  );
  render(<App />);
  await screen.findByText("第 2 轮练习 · 进行中");
  fireEvent.click(screen.getByRole("link", { name: "第 1 轮练习" }));
  await screen.findByText("成绩 90%（实际评分分母 15 题）");
  expect(window.location.search).toContain(`round=${round.test_id}`);
  fireEvent.click(screen.getByRole("link", { name: "第 2 轮练习 · 最近启动" }));
  await screen.findByText("第 2 轮练习 · 进行中");
  expect(
    screen.queryByText("成绩 90%（实际评分分母 15 题）"),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "第 1 轮练习" }));
  await screen.findByText("成绩 90%（实际评分分母 15 题）");
  fireEvent.click(screen.getByRole("button", { name: "开始新一轮练习" }));
  await screen.findByText("第 3 轮练习 · 进行中");
  expect(window.location.search).toContain("round=t3");
});

it("历史计划仅查看结果，不开放评分重试和重练", async () => {
  savedRequirements();
  state.editable = false;
  state.round = {
    ...round,
    status: "COMPLETED",
    answered_count: 15,
    graded_count: 13,
    unscored_count: 2,
    retry_available: true,
  };
  render(<App />);
  await screen.findByRole("link", { name: "查看本轮结果" });
  expect(
    screen.queryByRole("button", { name: "重试未评分题" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "重新练习" }),
  ).not.toBeInTheDocument();
});

it("已放弃历史轮仍提供只读卷面入口", async () => {
  savedRequirements();
  state.round = { ...round, test_id: "new-round", round_no: 2 };
  state.rounds = [state.round, { ...round, status: "ABANDONED" }];
  render(<App />);
  fireEvent.click(await screen.findByRole("link", { name: "第 1 轮练习" }));
  expect(
    await screen.findByRole("link", { name: "查看本轮结果" }),
  ).toHaveAttribute("href", round.paper_path + "?view=single");
});
