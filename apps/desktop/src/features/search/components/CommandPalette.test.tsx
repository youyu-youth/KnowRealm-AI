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
const UNCOURSE_RECORD_ID = "66666666-6666-4666-8666-666666666666";

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
    {
      course_name: null,
      id: UNCOURSE_RECORD_ID,
      title: "未归类速记",
      snippet: "代数 笔记",
      updated_at: "2026-09-03T08:00:00.000000Z",
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

// 记录详情页落地所需端点（口径同 inbox.test 的 mockRecordDetail + summary）。
function mockRecordDestination(recordId: string, withKnowledgePoints = false) {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
      HttpResponse.json({
        id: recordId,
        course_id: recordId === UNCOURSE_RECORD_ID ? null : COURSE_ID,
        capture_type: "QUICK_NOTE",
        title: recordId === RECORD_ID ? "傅里叶变换入门" : "未归类速记",
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

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

// 路由异步解析完成前 AppShell（含热键监听）尚未挂载，先等顶栏出现再触发热键。
async function openPaletteByHotkey() {
  await screen.findByRole("button", { name: "搜索" });
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
}

async function paletteInput() {
  return (await screen.findByPlaceholderText(
    "搜索课程、学习记录、知识点…",
  )) as HTMLInputElement;
}

// cmdk 无选中态的 ARIA 角色可查，键盘选中断言只能依赖其内部属性（无角色可用时的妥协）。
function selectedItemText(container: HTMLElement) {
  return container.querySelector("[cmdk-item][data-selected='true']")
    ?.textContent;
}

async function closeTopDialog(name: string) {
  fireEvent.keyDown(screen.getByRole("heading", { name }) as HTMLElement, {
    key: "Escape",
  });
  await waitFor(() =>
    expect(screen.queryByRole("heading", { name })).not.toBeInTheDocument(),
  );
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("命令面板", () => {
  it("Ctrl+K 唤起、Esc 关闭；Ctrl+Alt+K 不唤起；重开不带出上次查询", async () => {
    renderAt();
    await screen.findByRole("button", { name: "搜索" });

    // OS 全局快捷键（速记/录音为 Ctrl+Alt+*）不应被面板热键吞掉。
    fireEvent.keyDown(window, { key: "k", ctrlKey: true, altKey: true });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await openPaletteByHotkey();
    const input = await paletteInput();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "代数" } });

    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );

    await openPaletteByHotkey();
    expect((await paletteInput()).value).toBe("");
    expect(
      within(screen.getByRole("dialog")).getByText("开始录音"),
    ).toBeVisible();
  });

  it("标题栏搜索按钮位于最小化左侧并唤起同一面板", async () => {
    renderAt();

    const search = await screen.findByRole("button", { name: "搜索" });
    const titleBar = screen.getByRole("banner", { name: "窗口标题栏" });
    expect(within(titleBar).getByRole("button", { name: "搜索" })).toBe(search);
    expect(
      screen.queryByRole("banner", { name: "快速捕获" }),
    ).not.toBeInTheDocument();
    expect(search).not.toHaveAttribute("data-tauri-drag-region");
    expect(
      search.compareDocumentPosition(
        within(titleBar).getByRole("button", { name: "最小化" }),
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(search);
    expect(await paletteInput()).toBeInTheDocument();
  });

  it("空查询显示三个捕获命令且不发搜索请求，Enter 触发既有入口", async () => {
    mockSearch(emptyResults);
    renderAt();
    await openPaletteByHotkey();

    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText("开始录音")).toBeVisible();
    expect(within(dialog).getByText("新建速记")).toBeVisible();
    expect(within(dialog).getByText("粘贴文本")).toBeVisible();
    expect(searchRequests).toHaveLength(0);

    // 首项=开始录音：Enter 直接触发既有录音开始对话框。
    let input = await paletteInput();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(
      await screen.findByRole("heading", { name: "开始录音" }),
    ).toBeVisible();
    await closeTopDialog("开始录音");

    // 次项=新建速记。
    await openPaletteByHotkey();
    input = await paletteInput();
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(selectedItemText(screen.getByRole("dialog"))).toContain("新建速记");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(
      await screen.findByRole("heading", { name: "新建速记" }),
    ).toBeVisible();
    await closeTopDialog("新建速记");

    // 三项=粘贴文本，触发后面板关闭。
    await openPaletteByHotkey();
    input = await paletteInput();
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(
        screen.queryByPlaceholderText("搜索课程、学习记录、知识点…"),
      ).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByRole("heading", { name: "粘贴文本" }),
    ).toBeVisible();
    expect(searchRequests).toHaveLength(0);
  });

  it("↑↓ 在命令间循环移动（loop）", async () => {
    renderAt();
    await openPaletteByHotkey();

    const dialog = screen.getByRole("dialog");
    await paletteInput();
    expect(selectedItemText(dialog)).toContain("开始录音");

    const input = screen.getByPlaceholderText("搜索课程、学习记录、知识点…");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(selectedItemText(dialog)).toContain("新建速记");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(selectedItemText(dialog)).toContain("粘贴文本");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(selectedItemText(dialog)).toContain("开始录音");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(selectedItemText(dialog)).toContain("粘贴文本");
  });

  it("输入去抖 250ms 后才请求 /api/search，连续输入只发一次", async () => {
    mockSearch(searchResults);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代" } });
    fireEvent.change(input, { target: { value: "代数" } });
    expect(searchRequests).toHaveLength(0);

    await waitFor(() => expect(searchRequests).toHaveLength(1));
    expect(new URL(searchRequests[0]).searchParams.get("q")).toBe("代数");
    expect(new URL(searchRequests[0]).searchParams.get("limit")).toBeNull();
  });

  it("结果按 命令→课程→学习记录→知识点 分组混排，展示标题/摘录/课程名", async () => {
    mockSearch(searchResults);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代数" } });

    const dialog = screen.getByRole("dialog");
    await waitFor(() => {
      expect(within(dialog).getByText("傅里叶变换入门")).toBeVisible();
    });

    const headings = within(dialog)
      .getAllByText(
        (_, element) => element?.getAttribute("cmdk-group-heading") !== null,
      )
      .map((element) => element.textContent);
    expect(headings).toEqual(["课程", "学习记录", "知识点"]);

    expect(within(dialog).getByText("线性代数")).toBeVisible();
    // 记录项与知识点项的所属课程名上下文各一处。
    expect(within(dialog).getAllByText("高等数学")).toHaveLength(2);
    expect(within(dialog).getByText("未归类速记")).toBeVisible();
    // 查询词与命令文案无子串匹配时命令组隐藏。
    expect(within(dialog).queryByText("开始录音")).not.toBeInTheDocument();
  });

  it("命令项也参与混排：查询命中命令文案时命令组排在最前", async () => {
    mockSearch(searchResults);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "录音" } });

    const dialog = screen.getByRole("dialog");
    await waitFor(() => {
      expect(within(dialog).getByText("开始录音")).toBeVisible();
    });
    const headings = within(dialog)
      .getAllByText(
        (_, element) => element?.getAttribute("cmdk-group-heading") !== null,
      )
      .map((element) => element.textContent);
    expect(headings[0]).toBe("命令");
  });

  it("仅一类资产有结果时只渲染该分组，空分组不残留标题", async () => {
    mockSearch({
      courses: [],
      records: searchResults.records,
      knowledge_points: [],
    });
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代数" } });

    const dialog = screen.getByRole("dialog");
    await waitFor(() => {
      expect(within(dialog).getByText("傅里叶变换入门")).toBeVisible();
    });
    const headings = within(dialog)
      .getAllByText(
        (_, element) => element?.getAttribute("cmdk-group-heading") !== null,
      )
      .map((element) => element.textContent);
    expect(headings).toEqual(["学习记录"]);
  });

  it("无结果时展示空态提示", async () => {
    mockSearch(emptyResults);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "不存在的关键词" } });

    expect(await screen.findByText("没有找到相关内容")).toBeVisible();
  });

  it("课程结果跳转课程详情", async () => {
    mockSearch(searchResults);
    mockCourseDestination();
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代数" } });

    const dialog = screen.getByRole("dialog");
    fireEvent.click(await within(dialog).findByText("线性代数"));

    await screen.findByRole("heading", { name: "线性代数" });
    expect(window.location.pathname).toBe(`/spaces/${COURSE_ID}`);
    expect(window.location.search).toBe("?tab=overview");
    await waitFor(() =>
      expect(
        screen.queryByPlaceholderText("搜索课程、学习记录、知识点…"),
      ).not.toBeInTheDocument(),
    );
  });

  it("学习记录结果跳转记录详情", async () => {
    mockSearch(searchResults);
    mockRecordDestination(RECORD_ID);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代数" } });

    const dialog = screen.getByRole("dialog");
    fireEvent.click(await within(dialog).findByText("傅里叶变换入门"));

    await screen.findByRole("heading", { name: "傅里叶变换入门" });
    expect(window.location.pathname).toBe(`/records/${RECORD_ID}`);
    expect(window.location.search).toBe("");

    // 跳转关闭面板后重开：查询已重置，回到命令态。
    await openPaletteByHotkey();
    expect((await paletteInput()).value).toBe("");
    expect(
      within(screen.getByRole("dialog")).getByText("开始录音"),
    ).toBeVisible();
  });

  it("知识点结果跳转所属记录详情的知识点页签", async () => {
    mockSearch(searchResults);
    mockRecordDestination(RECORD_ID, true);
    renderAt();
    await openPaletteByHotkey();

    const input = await paletteInput();
    fireEvent.change(input, { target: { value: "代数" } });

    const dialog = screen.getByRole("dialog");
    fireEvent.click(await within(dialog).findByText("傅里叶级数"));

    await screen.findByRole("heading", { name: "傅里叶变换入门" });
    expect(window.location.pathname).toBe(`/records/${RECORD_ID}`);
    expect(window.location.search).toBe("?tab=knowledge-points");
  });
});
