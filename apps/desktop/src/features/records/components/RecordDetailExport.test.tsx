// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  chooseMarkdownSavePath,
  openExportedFile,
  writeMarkdownFile,
} from "@/services/tauri/learningAssetExport";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse, delay } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];
type SummaryOut = components["schemas"]["SummaryOut"];
type KnowledgePointOut = components["schemas"]["KnowledgePointOut"];
type QuizOut = components["schemas"]["QuizOut"];
type TodoOut = components["schemas"]["TodoOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const KNOWLEDGE_POINTS_URL = `${DETAIL_URL}/knowledge-points`;
const QUIZZES_URL = `${DETAIL_URL}/quizzes`;
const TODOS_URL = `${DETAIL_URL}/todos`;
const JOBS_URL = `${DETAIL_URL}/jobs`;
const TRANSCRIPT_URL = `${DETAIL_URL}/transcript`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const PREFERENCES_URL = `${TEST_SIDECAR_URL}/api/settings/preferences`;
const ROUTE_PATH = `/records/${RECORD_ID}`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: COURSE_ID,
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "COMPLETED",
  duration_ms: 65_000,
  summary_confirmed_at: "2026-08-25T08:30:00.000000Z",
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-25T08:30:00.000000Z",
};

const confirmedSummary: SummaryOut = {
  id: "55555555-5555-4555-8555-555555555555",
  record_id: RECORD_ID,
  version_no: 1,
  transcript_source_version: 1,
  topic: "进程调度",
  abstract: "调度器按照既定策略选择下一个获得处理器的进程。",
  sections: [{ heading: "核心机制", points: ["就绪队列决定候选顺序。"] }],
  status: "CONFIRMED",
  model: "qwen-plus",
  prompt_version: "summary-v1",
  user_feedback: null,
  created_at: "2026-08-24T12:00:00.000000Z",
};

function summaryResponse(summary: SummaryOut | null) {
  return HttpResponse.json({
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
    summary,
  });
}

function knowledgePoint(
  overrides: Partial<KnowledgePointOut> = {},
): KnowledgePointOut {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    record_id: RECORD_ID,
    batch_id: null,
    name: "进程调度",
    detail: "调度器从就绪队列中选择下一个运行的进程。",
    tags: ["操作系统"],
    importance: 5,
    generated_from_summary_id: null,
    generation_status: "ACTIVE",
    created_at: "2026-08-24T12:00:00.000000Z",
    updated_at: "2026-08-24T12:00:00.000000Z",
    ...overrides,
  };
}

function knowledgePointsResponse(items: KnowledgePointOut[]) {
  return HttpResponse.json({
    items,
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
    input_mode: null,
  });
}

function quiz(overrides: Partial<QuizOut> = {}): QuizOut {
  return {
    id: "77777777-7777-4777-8777-777777777777",
    record_id: RECORD_ID,
    batch_id: "88888888-8888-4888-8888-888888888888",
    generated_from_summary_id: confirmedSummary.id,
    generation_status: "ACTIVE",
    question_type: "MULTIPLE_CHOICE",
    stem: "哪个算法淘汰最久未使用的页面？",
    options: ["FIFO", "LRU", "Clock"],
    correct_answer: null,
    explanation: null,
    difficulty: "MEDIUM",
    user_answer: null,
    answer_result: null,
    answered_at: null,
    created_at: "2026-08-24T12:00:00.000000Z",
    updated_at: "2026-08-24T12:00:00.000000Z",
    ...overrides,
  };
}

function quizzesResponse(items: QuizOut[]) {
  return HttpResponse.json({
    items,
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
  });
}

function todo(overrides: Partial<TodoOut> = {}): TodoOut {
  return {
    id: "99999999-9999-4999-8999-999999999999",
    record_id: RECORD_ID,
    batch_id: null,
    content: "完成课后练习",
    status: "TODO",
    source: "MANUAL",
    generated_from_summary_id: null,
    generation_status: null,
    sort_order: 0,
    created_at: "2026-08-24T12:00:00.000000Z",
    updated_at: "2026-08-24T12:00:00.000000Z",
    ...overrides,
  };
}

function todosResponse(items: TodoOut[]) {
  return HttpResponse.json({
    items,
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
  });
}

const saveMock = vi.mocked(chooseMarkdownSavePath);
const writeTextFileMock = vi.mocked(writeMarkdownFile);
const openMock = vi.mocked(openExportedFile);

vi.mock("@/services/tauri/learningAssetExport", () => ({
  chooseMarkdownSavePath: vi.fn(),
  writeMarkdownFile: vi.fn(),
  openExportedFile: vi.fn(),
}));
vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  saveMock.mockReset();
  writeTextFileMock.mockReset();
  openMock.mockReset();
  server.use(
    http.get(DETAIL_URL, ({ request }) => {
      expect(request.headers.get("X-KnowRealm-Token")).toBe(TEST_LAUNCH_TOKEN);
      return HttpResponse.json(record);
    }),
    http.get(SUMMARY_URL, () => summaryResponse(confirmedSummary)),
    http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
    http.get(QUIZZES_URL, () => quizzesResponse([])),
    http.get(TODOS_URL, () => todosResponse([])),
    http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
    http.get(PREFERENCES_URL, () => HttpResponse.json({ quiz_last_count: 3 })),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path = ROUTE_PATH) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

async function openExportMenu() {
  fireEvent.click(await screen.findByRole("button", { name: "导出 Markdown" }));
  return screen.findByRole("menuitem", { name: /导出当前 Tab/ });
}

async function openAggregateExportMenu() {
  fireEvent.click(await screen.findByRole("button", { name: "导出 Markdown" }));
  return screen.findByRole("menuitem", { name: /导出全部学习资产/ });
}

const SAVED_PATH = "C:\\学习资料\\操作系统第一讲-总结.md";

describe("学习资产 Markdown 导出", () => {
  it("聚合导出并行读取四类最新事实，按固定顺序保存不可变快照", async () => {
    const reads = { summary: 0, knowledgePoints: 0, quizzes: 0, todos: 0 };
    server.use(
      http.get(SUMMARY_URL, () => {
        reads.summary += 1;
        return summaryResponse(confirmedSummary);
      }),
      http.get(KNOWLEDGE_POINTS_URL, () => {
        reads.knowledgePoints += 1;
        return knowledgePointsResponse([knowledgePoint()]);
      }),
      http.get(QUIZZES_URL, () => {
        reads.quizzes += 1;
        return quizzesResponse([quiz()]);
      }),
      http.get(TODOS_URL, () => {
        reads.todos += 1;
        return todosResponse([todo()]);
      }),
    );
    saveMock.mockResolvedValue("C:\\学习资料\\操作系统第一讲-学习资产.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    await waitFor(() => expect(reads.summary).toBeGreaterThan(0));
    const readsBeforeExport = { ...reads };
    fireEvent.click(await openAggregateExportMenu());

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(reads.summary).toBeGreaterThan(readsBeforeExport.summary);
    expect(reads.knowledgePoints).toBeGreaterThan(
      readsBeforeExport.knowledgePoints,
    );
    expect(reads.quizzes).toBeGreaterThan(readsBeforeExport.quizzes);
    expect(reads.todos).toBeGreaterThan(readsBeforeExport.todos);
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-学习资产.md");
    const markdown = writeTextFileMock.mock.calls[0][1];
    expect(markdown).toMatch(
      /## 总结[\s\S]*## 知识点[\s\S]*## 习题[\s\S]*## Todo/,
    );
    expect(markdown.match(/^# /gm)).toHaveLength(1);
    expect(markdown).not.toMatch(/正确答案|解析/);
  });

  it("聚合导出自然省略尚未生成的资产", async () => {
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(null)),
      http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
      http.get(QUIZZES_URL, () => quizzesResponse([quiz()])),
      http.get(TODOS_URL, () => todosResponse([])),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-学习资产.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    fireEvent.click(await openAggregateExportMenu());

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    const markdown = writeTextFileMock.mock.calls[0][1];
    expect(markdown).toContain("## 习题");
    expect(markdown).not.toMatch(/## 总结|## 知识点|## Todo/);
  });

  it("聚合最新读取确认全部为空时提示暂无内容且不打开保存对话框", async () => {
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(null)),
      http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
      http.get(QUIZZES_URL, () => quizzesResponse([])),
      http.get(TODOS_URL, () => todosResponse([])),
    );
    renderAt();

    fireEvent.click(await openAggregateExportMenu());

    expect(await screen.findByRole("status")).toHaveTextContent(
      "暂无可导出内容",
    );
    expect(saveMock).not.toHaveBeenCalled();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("聚合任一读取失败时整次失败且不打开保存对话框", async () => {
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(confirmedSummary)),
      http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json({ detail: "数据库暂时繁忙" }, { status: 500 }),
      ),
      http.get(TODOS_URL, () => todosResponse([todo()])),
    );
    renderAt();

    fireEvent.click(await openAggregateExportMenu());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "读取学习资产失败，未导出文件",
    );
    expect(saveMock).not.toHaveBeenCalled();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("聚合响应不可解释时按读取失败处理", async () => {
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(confirmedSummary)),
      http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
      http.get(QUIZZES_URL, () => HttpResponse.json({})),
      http.get(TODOS_URL, () => todosResponse([])),
    );
    renderAt();

    fireEvent.click(await openAggregateExportMenu());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "读取学习资产失败，未导出文件",
    );
    expect(saveMock).not.toHaveBeenCalled();
  });

  it.each([{}, { summary: {} }, { summary: [] }])(
    "聚合 Summary 响应不可解释时按读取失败处理：%o",
    async (response) => {
      let summaryGets = 0;
      server.use(
        http.get(SUMMARY_URL, () => {
          summaryGets += 1;
          return summaryGets === 1
            ? summaryResponse(confirmedSummary)
            : HttpResponse.json(response);
        }),
        http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
        http.get(QUIZZES_URL, () => quizzesResponse([])),
        http.get(TODOS_URL, () => todosResponse([])),
      );
      renderAt();

      fireEvent.click(await openAggregateExportMenu());

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "读取学习资产失败，未导出文件",
      );
      expect(saveMock).not.toHaveBeenCalled();
    },
  );

  it("四类缓存事实均已知且全部为空时禁用聚合导出", async () => {
    const reads = { knowledgePoints: 0, quizzes: 0, todos: 0 };
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(null)),
      http.get(KNOWLEDGE_POINTS_URL, () => {
        reads.knowledgePoints += 1;
        return knowledgePointsResponse([]);
      }),
      http.get(QUIZZES_URL, () => {
        reads.quizzes += 1;
        return quizzesResponse([]);
      }),
      http.get(TODOS_URL, () => {
        reads.todos += 1;
        return todosResponse([]);
      }),
    );
    renderAt();

    fireEvent.click(await screen.findByRole("tab", { name: "知识点" }));
    await waitFor(() => expect(reads.knowledgePoints).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("tab", { name: "习题" }));
    await waitFor(() => expect(reads.quizzes).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("tab", { name: "Todo" }));
    await waitFor(() => expect(reads.todos).toBeGreaterThan(0));

    const item = await openAggregateExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("暂无可导出内容");
  });

  it("聚合读取完成后冻结快照，保存对话框停留期间的新事实不进入文件", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, () => {
        summaryGets += 1;
        return summaryResponse({
          ...confirmedSummary,
          topic: summaryGets > 2 ? "保存期间的新主题" : "点击时的主题",
        });
      }),
      http.get(KNOWLEDGE_POINTS_URL, () => knowledgePointsResponse([])),
      http.get(QUIZZES_URL, () => quizzesResponse([])),
      http.get(TODOS_URL, () => todosResponse([])),
    );
    let finishSave: (path: string) => void = (path) => {
      throw new Error(`保存对话框尚未就绪：${path}`);
    };
    saveMock.mockImplementation(
      () => new Promise((resolve) => (finishSave = resolve)),
    );
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    fireEvent.click(await openAggregateExportMenu());
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    server.use(
      http.get(SUMMARY_URL, () =>
        summaryResponse({ ...confirmedSummary, topic: "保存期间的新主题" }),
      ),
    );
    finishSave("D:\\资料\\操作系统第一讲-学习资产.md");

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(writeTextFileMock.mock.calls[0][1]).toContain("点击时的主题");
    expect(writeTextFileMock.mock.calls[0][1]).not.toContain(
      "保存期间的新主题",
    );
  });

  it("聚合导出进行中禁用重复触发并只打开一个保存对话框", async () => {
    server.use(
      http.get(SUMMARY_URL, () => summaryResponse(confirmedSummary)),
      http.get(KNOWLEDGE_POINTS_URL, async () => {
        await delay(400);
        return knowledgePointsResponse([]);
      }),
      http.get(QUIZZES_URL, () => quizzesResponse([])),
      http.get(TODOS_URL, () => todosResponse([])),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-学习资产.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    fireEvent.click(await openAggregateExportMenu());

    expect(await screen.findByText("正在导出…")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "导出 Markdown" }),
    ).toBeDisabled();
    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledTimes(1);
  });

  it("Summary 导出：最新读取后组装快照，经保存对话框写入并显示成功与打开动作", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-总结.md");
    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(writeTextFileMock).toHaveBeenCalledWith(
      SAVED_PATH,
      [
        "# 操作系统第一讲",
        "",
        "## 总结",
        "",
        "**主题**：进程调度",
        "",
        "**摘要**：调度器按照既定策略选择下一个获得处理器的进程。",
        "",
        "### 核心机制",
        "",
        "- 就绪队列决定候选顺序。",
        "",
      ].join("\n"),
    );
    expect(
      await screen.findByText(`已保存：${SAVED_PATH}`),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开文件" }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith(SAVED_PATH));
  });

  it("每次触发都重新读取当前资产而非依赖缓存", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, () => {
        summaryGets += 1;
        return summaryResponse(confirmedSummary);
      }),
    );
    saveMock.mockResolvedValue(null);
    renderAt();

    const readsAfterMount = async () => {
      await waitFor(() => expect(summaryGets).toBeGreaterThan(0));
      return summaryGets;
    };
    const initial = await readsAfterMount();

    let item = await openExportMenu();
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    const afterFirstExport = summaryGets;
    expect(afterFirstExport).toBeGreaterThan(initial);

    item = await openExportMenu();
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(2));
    expect(summaryGets).toBeGreaterThan(afterFirstExport);
  });

  it("未确认总结时单项导出禁用并说明原因", async () => {
    server.use(
      http.get(SUMMARY_URL, () =>
        summaryResponse({ ...confirmedSummary, status: "GENERATED" }),
      ),
    );
    renderAt();

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("总结尚未确认，不能导出");
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).not.toHaveBeenCalled());
  });

  it("还没有总结时单项导出禁用并说明原因", async () => {
    server.use(http.get(SUMMARY_URL, () => summaryResponse(null)));
    renderAt();

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有总结");
  });

  it("当前 Tab 不支持导出时禁用并说明原因", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("当前 Tab 暂不支持导出");
  });

  it("知识点导出仅包含 ACTIVE 项并沿用页面顺序，默认名以知识点结尾", async () => {
    server.use(
      http.get(KNOWLEDGE_POINTS_URL, () =>
        knowledgePointsResponse([
          knowledgePoint({
            id: "a",
            name: "候选不该出现",
            generation_status: "DRAFT",
            batch_id: "33333333-3333-4333-8333-333333333333",
          }),
          knowledgePoint({ id: "b", name: "进程调度", importance: 5 }),
          knowledgePoint({
            id: "c",
            name: "过时批次不该出现",
            generation_status: "SUPERSEDED",
          }),
          knowledgePoint({
            id: "d",
            name: "时间片",
            detail: "时间片轮转防止单一进程垄断处理器。",
            importance: 4,
            tags: [],
          }),
        ]),
      ),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-知识点.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(item);

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-知识点.md");
    const [, markdown] = writeTextFileMock.mock.calls[0];
    expect(markdown).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## 知识点",
        "",
        "### 进程调度",
        "",
        "调度器从就绪队列中选择下一个运行的进程。",
        "",
        "- 重要度：5/5",
        "- 标签：操作系统",
        "",
        "### 时间片",
        "",
        "时间片轮转防止单一进程垄断处理器。",
        "",
        "- 重要度：4/5",
        "",
      ].join("\n"),
    );
  });

  it("没有正式知识点时单项导出禁用并说明原因", async () => {
    server.use(
      http.get(KNOWLEDGE_POINTS_URL, () =>
        knowledgePointsResponse([
          knowledgePoint({ generation_status: "DRAFT" }),
        ]),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有正式知识点");
  });

  it("习题导出：菜单可用、触发时重新读取且只保存 ACTIVE 题", async () => {
    let reads = 0;
    server.use(
      http.get(QUIZZES_URL, () => {
        reads += 1;
        return quizzesResponse([
          quiz({ id: "draft", generation_status: "DRAFT" }),
          quiz({ id: "active" }),
          quiz({ id: "old", generation_status: "SUPERSEDED" }),
        ]);
      }),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-习题.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    const readsAfterMount = reads;
    fireEvent.click(item);

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(reads).toBeGreaterThan(readsAfterMount);
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-习题.md");
    const [, markdown] = writeTextFileMock.mock.calls[0];
    expect(markdown).toContain("## 习题");
    expect(markdown).toContain("哪个算法淘汰最久未使用的页面？");
    expect(markdown.match(/^### /gm)).toHaveLength(1);
    expect(markdown).not.toMatch(/正确答案|解析/);
  });

  it("Todo 导出：菜单可用、触发时重新读取并保存正式混排清单", async () => {
    let reads = 0;
    server.use(
      http.get(TODOS_URL, () => {
        reads += 1;
        return todosResponse([
          todo({
            id: "done-ai",
            content: "完成课后练习",
            status: "DONE",
            source: "AI",
            generation_status: "ACTIVE",
            sort_order: 2,
          }),
          todo({ id: "manual", content: "补充笔记", sort_order: 1 }),
          todo({
            id: "draft",
            generation_status: "DRAFT",
            source: "AI",
            sort_order: 0,
          }),
        ]);
      }),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-Todo.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt(`${ROUTE_PATH}?tab=todo`);

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    const readsAfterMount = reads;
    fireEvent.click(item);

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(reads).toBeGreaterThan(readsAfterMount);
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-Todo.md");
    expect(writeTextFileMock.mock.calls[0][1]).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## Todo",
        "",
        "- [ ] 补充笔记",
        "- [x] 完成课后练习",
        "",
      ].join("\n"),
    );
  });

  it("没有 ACTIVE 习题时禁用导出且不进入保存流程", async () => {
    server.use(
      http.get(QUIZZES_URL, () =>
        quizzesResponse([quiz({ generation_status: "DRAFT" })]),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有正式习题");
    fireEvent.click(item);
    expect(saveMock).not.toHaveBeenCalled();
  });

  it("没有正式 Todo 时禁用导出且不进入保存流程", async () => {
    server.use(
      http.get(TODOS_URL, () =>
        todosResponse([todo({ generation_status: "SUPERSEDED" })]),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有正式 Todo");
    fireEvent.click(item);
    expect(saveMock).not.toHaveBeenCalled();
  });

  it("习题最新读取失败时显示错误，不伪装成空内容", async () => {
    let reads = 0;
    server.use(
      http.get(QUIZZES_URL, () => {
        reads += 1;
        return reads === 1
          ? quizzesResponse([quiz()])
          : HttpResponse.json({ detail: "数据库暂时繁忙" }, { status: 500 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    const item = await openExportMenu();
    fireEvent.click(item);

    expect(
      await screen.findByRole("alert", {}, { timeout: 4_000 }),
    ).toHaveTextContent("读取学习资产失败，未导出文件");
    expect(saveMock).not.toHaveBeenCalled();
  });

  it("聚合导出取消保存时不写文件、不报错、不显示成功", async () => {
    saveMock.mockResolvedValue(null);
    renderAt();

    const item = await openAggregateExportMenu();
    fireEvent.click(item);

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("读取失败时显示页内错误且不进入保存流程", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, () => {
        summaryGets += 1;
        // 首次挂载读取成功让菜单可用，之后的每次读取都失败
        return summaryGets === 1
          ? summaryResponse(confirmedSummary)
          : HttpResponse.json({ detail: "数据库暂时繁忙" }, { status: 500 });
      }),
    );
    renderAt();

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(item);

    expect(
      await screen.findByRole("alert", {}, { timeout: 4_000 }),
    ).toHaveTextContent("读取学习资产失败，未导出文件");
    expect(saveMock).not.toHaveBeenCalled();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("聚合导出写入失败时显示页内错误且不出现成功状态", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockRejectedValue(
      new Error("failed to write file: Access Denied"),
    );
    renderAt();

    const item = await openAggregateExportMenu();
    fireEvent.click(item);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "文件写入失败，未保存",
    );
    expect(screen.queryByText(/已保存/)).not.toBeInTheDocument();
  });

  it("聚合保存对话框以异常结束时按写入失败提示，不停留在导出中", async () => {
    saveMock.mockRejectedValue(new Error("dialog plugin error"));
    renderAt();

    const item = await openAggregateExportMenu();
    fireEvent.click(item);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "文件写入失败，未保存",
    );
    expect(screen.queryByText("正在导出…")).not.toBeInTheDocument();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("聚合保存成功后打开文件失败单独提示，不推翻已保存事实", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    openMock.mockRejectedValue(new Error("no application"));
    renderAt();

    const item = await openAggregateExportMenu();
    fireEvent.click(item);

    fireEvent.click(await screen.findByRole("button", { name: "打开文件" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("无法打开文件");
    expect(screen.getByText(`已保存：${SAVED_PATH}`)).toBeInTheDocument();
  });

  it("导出进行中阻止重复触发", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, async () => {
        summaryGets += 1;
        // 挂载读取即时返回让菜单立即可用，导出触发的重新读取延迟进行
        if (summaryGets > 1) await delay(400);
        return summaryResponse(confirmedSummary);
      }),
    );
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    const item = await openExportMenu();
    expect(item).not.toBeDisabled();
    fireEvent.click(item);

    expect(
      await screen.findByText("正在导出…", {}, { timeout: 3_000 }),
    ).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "导出 Markdown" });
    expect(trigger).toBeDisabled();

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledTimes(1);
  });
});
