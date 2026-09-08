// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import type { SearchOut } from "@/features/search/api/search";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

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

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const RECORD_ID = "22222222-2222-4222-8222-222222222222";

const searchResults: SearchOut = {
  courses: [
    {
      id: COURSE_ID,
      title: "线性代数",
      snippet: "线性 代数",
      updated_at: "2026-09-01T08:00:00.000000Z",
    },
  ],
  records: [
    {
      course_name: "高等数学",
      id: RECORD_ID,
      title: "傅里叶变换入门",
      snippet: "讲过 傅里叶 变换 的 一节课",
      updated_at: "2026-09-02T08:00:00.000000Z",
    },
  ],
  knowledge_points: [
    {
      course_name: "高等数学",
      id: "44444444-4444-4444-8444-444444444444",
      record_id: RECORD_ID,
      title: "傅里叶级数",
      snippet: "周期 函数 的 级数 展开",
      updated_at: "2026-09-02T09:00:00.000000Z",
    },
  ],
};

const onlyRecordsResults: SearchOut = {
  courses: [],
  records: searchResults.records,
  knowledge_points: [],
};

const emptyResults: SearchOut = {
  courses: [],
  records: [],
  knowledge_points: [],
};

const searchRequests: string[] = [];

function mockSearch(response: SearchOut) {
  searchRequests.length = 0;
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/search`, ({ request }) => {
      searchRequests.push(request.url);
      return HttpResponse.json(response);
    }),
  );
}

// 记录详情页落地所需端点（口径同命令面板测试的 mockRecordDestination）。
function mockRecordDestination(recordId: string, withKnowledgePoints = false) {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
      HttpResponse.json({
        id: recordId,
        course_id: COURSE_ID,
        capture_type: "QUICK_NOTE",
        title: "傅里叶变换入门",
        status: "NOTE",
        duration_ms: 0,
        summary_confirmed_at: null,
        created_at: "2026-09-02T08:00:00.000000Z",
        updated_at: "2026-09-02T08:00:00.000000Z",
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/jobs`, () =>
      HttpResponse.json({ jobs: [], progress: 1 }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/transcript`, () =>
      HttpResponse.json({
        status: "READY",
        transcript: {
          language: "und",
          content: "速记正文",
          source_version: 1,
          edited_by_user: false,
          updated_at: "2026-09-02T08:00:01.000000Z",
        },
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/summary`, () =>
      HttpResponse.json({
        summary: null,
        action_required: "CONFIGURE_PROVIDER",
      }),
    ),
  );
  if (withKnowledgePoints) {
    const knowledgePoint: components["schemas"]["KnowledgePointOut"] = {
      id: "44444444-4444-4444-8444-444444444444",
      record_id: recordId,
      batch_id: "55555555-5555-4555-8555-555555555555",
      name: "傅里叶级数",
      detail: "周期函数的级数展开。",
      tags: ["高等数学"],
      importance: 5,
      generated_from_summary_id: "77777777-7777-4777-8777-777777777777",
      generation_status: "DRAFT",
      created_at: "2026-09-02T09:00:00.000000Z",
      updated_at: "2026-09-02T09:00:00.000000Z",
    };
    server.use(
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${recordId}/knowledge-points`,
        () => HttpResponse.json([knowledgePoint]),
      ),
    );
  }
}

function mockCourseDestination() {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`, () =>
      HttpResponse.json({
        id: COURSE_ID,
        name: "线性代数",
        learning_context: "SCHOOL",
        education_stage: "UNDERGRADUATE",
        depth: null,
        course_type: "MAJOR",
        description: null,
        status: "ACTIVE",
        created_at: "2026-08-20T08:00:00.000000Z",
        updated_at: "2026-08-20T08:00:00.000000Z",
      }),
    ),
  );
}

function renderAt(path = "/library") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

async function libraryInput() {
  // 路由异步解析完成前页面尚未挂载，用 findBy 等待输入框出现。
  return (await screen.findByRole("searchbox", {
    name: "搜索资产",
  })) as HTMLInputElement;
}

async function searchFor(keyword: string) {
  fireEvent.change(await libraryInput(), { target: { value: keyword } });
  await waitFor(() => expect(searchRequests).toHaveLength(1));
}

function visibleGroupHeadings() {
  return ["学习记录", "知识点", "课程"].filter((heading) =>
    screen.queryByRole("heading", { name: heading }),
  );
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("资产库视图", () => {
  it("侧栏资产库入口激活并可直达 /library", async () => {
    renderAt("/");
    fireEvent.click(await screen.findByRole("link", { name: "资产库" }));

    await screen.findByRole("heading", { name: "资产库" });
    expect(window.location.pathname).toBe("/library");
  });

  it("空查询显示引导卡而非空白，且不发起搜索请求", async () => {
    mockSearch(emptyResults);
    renderAt();

    expect(await screen.findByText("资产库还是空的")).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "搜索资产" })).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByText("正在搜索…")).not.toBeInTheDocument(),
    );
    expect(searchRequests).toHaveLength(0);
  });

  it("输入去抖后调 /api/search，带更大的每类 limit", async () => {
    mockSearch(searchResults);
    renderAt();

    await searchFor("代数");

    expect(new URL(searchRequests[0]).searchParams.get("q")).toBe("代数");
    expect(new URL(searchRequests[0]).searchParams.get("limit")).toBe("50");
    expect(await screen.findByText("傅里叶变换入门")).toBeVisible();
  });

  it("全部页签按 学习记录→知识点→课程 分组展示", async () => {
    mockSearch(searchResults);
    renderAt();

    await searchFor("代数");
    await screen.findByText("傅里叶变换入门");

    expect(visibleGroupHeadings()).toEqual(["学习记录", "知识点", "课程"]);
    expect(screen.getByText("傅里叶级数")).toBeVisible();
    expect(screen.getByText("线性代数")).toBeVisible();
  });

  it("类型页签在展示层过滤对应组，切换落 URL 且不重发请求", async () => {
    mockSearch(searchResults);
    renderAt();

    await searchFor("代数");
    await screen.findByText("傅里叶变换入门");

    // 页签经 navigate 更新 URL，断言等待路由状态落地。
    fireEvent.click(screen.getByRole("tab", { name: "知识点" }));
    await waitFor(() => expect(visibleGroupHeadings()).toEqual(["知识点"]));
    expect(screen.getByText("傅里叶级数")).toBeVisible();
    expect(screen.queryByText("傅里叶变换入门")).not.toBeInTheDocument();
    // 页签是 URL 状态：切换落 search params，可刷新恢复。
    expect(window.location.search).toBe("?tab=knowledgePoints");

    fireEvent.click(screen.getByRole("tab", { name: "课程" }));
    await waitFor(() => expect(visibleGroupHeadings()).toEqual(["课程"]));
    expect(window.location.search).toBe("?tab=courses");

    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    await waitFor(() =>
      expect(visibleGroupHeadings()).toEqual(["学习记录", "知识点", "课程"]),
    );
    expect(window.location.search).toBe("");
    expect(searchRequests).toHaveLength(1);
  });

  it("当前页签无匹配而其他类型有结果时给出过滤空组提示", async () => {
    mockSearch(onlyRecordsResults);
    renderAt();

    await searchFor("代数");
    await screen.findByText("傅里叶变换入门");

    fireEvent.click(screen.getByRole("tab", { name: "课程" }));
    expect(
      await screen.findByText("该类型下没有匹配结果", { exact: false }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    await waitFor(() => expect(visibleGroupHeadings()).toEqual(["学习记录"]));
    expect(
      screen.queryByText("该类型下没有匹配结果", { exact: false }),
    ).not.toBeInTheDocument();
  });

  it("有查询但无任何结果时展示明确空态提示", async () => {
    mockSearch(emptyResults);
    renderAt();

    await searchFor("不存在的关键词");

    expect(await screen.findByText("没有找到相关内容")).toBeVisible();
  });

  it("课程结果跳转课程详情", async () => {
    mockSearch(searchResults);
    mockCourseDestination();
    renderAt();

    await searchFor("代数");
    fireEvent.click(await screen.findByText("线性代数"));

    await screen.findByRole("heading", { name: "线性代数" });
    expect(window.location.pathname).toBe(`/spaces/${COURSE_ID}`);
    expect(window.location.search).toBe("?tab=overview");
  });

  it("学习记录结果跳转记录详情", async () => {
    mockSearch(searchResults);
    mockRecordDestination(RECORD_ID);
    renderAt();

    await searchFor("代数");
    fireEvent.click(await screen.findByText("傅里叶变换入门"));

    await screen.findByRole("heading", { name: "傅里叶变换入门" });
    expect(window.location.pathname).toBe(`/records/${RECORD_ID}`);
    expect(window.location.search).toBe("");
  });

  it("知识点结果跳转所属记录详情的知识点页签", async () => {
    mockSearch(searchResults);
    mockRecordDestination(RECORD_ID, true);
    renderAt();

    await searchFor("代数");
    fireEvent.click(await screen.findByText("傅里叶级数"));

    await screen.findByRole("heading", { name: "傅里叶变换入门" });
    expect(window.location.pathname).toBe(`/records/${RECORD_ID}`);
    expect(window.location.search).toBe("?tab=knowledge-points");
  });
});
