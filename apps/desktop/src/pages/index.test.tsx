// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
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
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const CONFIRM_URL = `${DETAIL_URL}/summary-confirmations`;
const TODAY_URL = `${TEST_SIDECAR_URL}/api/today/pending-summaries`;

const todo = {
  record_id: RECORD_ID,
  title: "操作系统第一讲",
  course_id: COURSE_ID,
  course_name: "操作系统",
  ready_at: "2026-08-23T12:00:00.000000Z",
};

const generatedSummary = {
  id: "44444444-4444-4444-8444-444444444444",
  record_id: RECORD_ID,
  version_no: 1,
  status: "GENERATED",
  transcript_source_version: 1,
  topic: "进程调度",
  abstract: "调度器按照既定策略选择下一个获得处理器的进程。",
  sections: [{ heading: "核心机制", points: ["就绪队列决定候选顺序。"] }],
  prompt_version: "summary-v1",
  model: "qwen-plus",
  user_feedback: null,
  created_at: "2026-08-23T10:00:00Z",
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
    http.get(SUMMARY_URL, () =>
      HttpResponse.json({
        action_required: "NONE",
        active_job_id: null,
        blocked_reason: null,
        summary: null,
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

describe("今日页", () => {
  it("速记保存后仍停留今日页，并刷新最近资料", async () => {
    let saved = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/library/items`, () =>
        HttpResponse.json({
          items: saved
            ? [
                {
                  id: "quick-source",
                  title: "刚刚保存的速记",
                  source_type: "TEXT",
                  availability: "RETRIEVABLE",
                  created_at: "2026-10-20T02:00:00Z",
                },
              ]
            : [],
          total: saved ? 1 : 0,
          backfill: null,
        }),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/text-captures`, () => {
        saved = true;
        return HttpResponse.json(
          { record_id: RECORD_ID, summary_job_id: null },
          { status: 202 },
        );
      }),
    );
    renderAt();
    expect(await screen.findByText("暂无最近资料")).toBeVisible();
    fireEvent.click(
      within(screen.getByRole("region", { name: "快速捕获" })).getByRole(
        "button",
        { name: "新建速记" },
      ),
    );
    const dialog = await screen.findByRole("dialog", { name: "新建速记" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "正文" }), {
      target: { value: "刚刚保存的速记" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const region = screen.getByRole("region", { name: "最近资料" });
    expect(await within(region).findByText("刚刚保存的速记")).toBeVisible();
    expect(window.location.pathname).toBe("/");
  });

  it("从计划项窗口专注任务后关闭窗口，并将焦点移至专注区", async () => {
    const tasks = Array.from({ length: 4 }, (_, index) => ({
      item_id: `focus-task-${index}`,
      plan_id: "plan",
      course_id: COURSE_ID,
      course_name: "操作系统",
      goal_id: "goal",
      goal_title: "比较进程调度策略",
      action_type: "STUDY_RECORD",
      content: `调度练习 ${index + 1}`,
      scheduled_date: "2026-10-19",
      estimated_minutes: 30,
      user_locked: false,
    }));
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/today/plan-items`, () =>
        HttpResponse.json(tasks),
      ),
    );
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: /查看更多/ }));
    const dialog = await screen.findByRole("dialog", { name: "今日计划项" });
    const fourth = within(dialog).getAllByRole("listitem")[3];
    fireEvent.click(within(fourth).getByRole("button", { name: "专注此任务" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("task")).toBe(
        tasks[3].item_id,
      ),
    );
    const focusTitle = screen.getByRole("heading", { name: "当前专注" });
    await waitFor(() => expect(focusTitle).toHaveFocus());
    expect(focusTitle.closest("section")).toHaveTextContent(tasks[3].content);
  });

  it("最近资料不再联动示例，临时笔记与计时状态跨视图保留", async () => {
    renderAt();
    const recentMaterials = await screen.findByRole("region", {
      name: "最近资料",
    });
    expect(
      await within(recentMaterials).findByText("暂无最近资料"),
    ).toBeVisible();
    expect(within(recentMaterials).queryByText("示意")).not.toBeInTheDocument();
    const materials = screen.getByRole("region", { name: "学习资料" });
    fireEvent.click(
      within(materials).getByRole("button", { name: "下一份示例资料" }),
    );
    expect(
      within(materials).getByRole("heading", { name: "MySQL 初始化脚本" }),
    ).toBeVisible();
    fireEvent.click(
      within(materials).getByRole("button", { name: "下一份示例资料" }),
    );
    expect(
      within(materials).getByRole("heading", { name: "Nginx 静态站点配置" }),
    ).toBeVisible();
    fireEvent.click(within(materials).getByRole("tab", { name: "随手笔记" }));
    fireEvent.change(within(materials).getByRole("textbox"), {
      target: { value: "比较命名卷与绑定挂载" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    fireEvent.click(screen.getByRole("tab", { name: /学习轨道/ }));
    await screen.findByRole("heading", { name: "学习趋势" });
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
    expect(within(materials).getByRole("textbox")).toHaveValue(
      "比较命名卷与绑定挂载",
    );
    fireEvent.click(screen.getByRole("tab", { name: /工作台/ }));
    expect(screen.getByRole("button", { name: "暂停" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "结束" }));
  });

  it("旧分区链接同时显示行动和待处理，切换学习轨道不再切换分区", async () => {
    renderAt("/?panel=pending");
    expect(
      await screen.findByRole("heading", { name: "待处理" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "待办事项" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "待处理" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "待办事项" }),
    ).not.toBeInTheDocument();
    const focus = screen.getByRole("button", { name: "当前专注" });
    fireEvent.click(focus);
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get("inspector")).toBe(
        "focus",
      ),
    );
    expect(screen.getByRole("heading", { name: "待处理" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "待办事项" })).toBeVisible();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(focus).toHaveFocus());
    fireEvent.click(screen.getByRole("tab", { name: /学习轨道/ }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "学习趋势" })).toBeVisible(),
    );
    expect(screen.getByRole("heading", { name: "待处理" })).toBeVisible();
    expect(
      new URLSearchParams(window.location.search).get("inspector"),
    ).toBeNull();
  });

  it("点击待确认记录直接打开详情，不再请求或展示今日总结预览", async () => {
    let previewReads = 0;
    const second = { ...todo, record_id: "second-record", title: "第二份总结" };
    server.use(
      http.get(SUMMARY_URL, () => {
        previewReads += 1;
        return HttpResponse.json({
          summary: generatedSummary,
          action_required: "NONE",
        });
      }),
      http.get(TODAY_URL, () => HttpResponse.json([todo, second])),
      http.get(`${TEST_SIDECAR_URL}/api/records/second-record/summary`, () => {
        previewReads += 1;
        return HttpResponse.json({
          summary: generatedSummary,
          action_required: "NONE",
        });
      }),
      http.get(`${TEST_SIDECAR_URL}/api/records/second-record`, () =>
        HttpResponse.json({ detail: "记录不存在" }, { status: 404 }),
      ),
    );
    renderAt();
    const link = await screen.findByRole("link", {
      name: "打开记录「第二份总结」",
    });
    expect(previewReads).toBe(0);
    expect(
      screen.queryByRole("region", { name: "待确认总结" }),
    ).not.toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/records/second-record");
    fireEvent.click(within(link).getByText("操作系统"));
    await waitFor(() =>
      expect(window.location.pathname).toBe("/records/second-record"),
    );
    expect(previewReads).toBe(0);
  });

  it("待处理按页浏览，切换筛选重置页码并保存在地址栏", async () => {
    server.use(
      http.get(TODAY_URL, () =>
        HttpResponse.json(
          Array.from({ length: 5 }, (_, i) => ({
            ...todo,
            record_id: `pending-${i}`,
            title: `待处理记录 ${i + 1}`,
          })),
        ),
      ),
    );
    renderAt();
    const list = await screen.findByRole("list", { name: "待处理记录列表" });
    await within(list).findByRole("link", { name: "打开记录「待处理记录 1」" });
    expect(within(list).getAllByRole("link")).toHaveLength(2);
    const pagination = screen.getByRole("navigation", {
      name: "待处理记录分页",
    });
    expect(
      within(pagination).getByRole("button", { name: "上一页" }),
    ).toBeDisabled();
    fireEvent.click(within(pagination).getByRole("button", { name: "下一页" }));
    expect(
      await within(list).findByRole("link", {
        name: "打开记录「待处理记录 3」",
      }),
    ).toBeVisible();
    expect(
      new URLSearchParams(window.location.search).get("pending_page"),
    ).toBe("2");
    fireEvent.click(screen.getByRole("tab", { name: /处理中\s*0/ }));
    expect(await screen.findByText("这个分类暂无待处理事项")).toBeVisible();
    expect(
      new URLSearchParams(window.location.search).get("pending_page"),
    ).toBe("1");
    expect(
      new URLSearchParams(window.location.search).get("pending_filter"),
    ).toBe("processing");
  });

  it("过期的总结预览链接不会重新打开预览，超出页码回到最后一页", async () => {
    server.use(http.get(TODAY_URL, () => HttpResponse.json([todo])));
    renderAt(
      "/?panel=review&inspector=summary&pending_filter=summary&pending_page=99",
    );
    expect(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    ).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "待确认总结" }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        new URLSearchParams(window.location.search).get("pending_page"),
      ).toBe("1"),
    );
  });

  it("待处理去重已就绪记录，保留处理中和失败状态及原文入口", async () => {
    server.use(
      http.get(TODAY_URL, () => HttpResponse.json([todo])),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          {
            id: RECORD_ID,
            course_id: COURSE_ID,
            title: todo.title,
            status: "SUMMARY_READY",
            capture_type: "DOCUMENT_IMPORT",
          },
          {
            id: "processing-record",
            title: "课堂录音",
            status: "CONTENT_PROCESSING",
            capture_type: "RECORDING",
          },
          {
            id: "failed-record",
            title: "失败网页",
            status: "FAILED",
            capture_type: "CLIP",
          },
          {
            id: "completed-record",
            title: "已完成记录",
            status: "COMPLETED",
            capture_type: "QUICK_NOTE",
          },
        ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/failed-record`, () =>
        HttpResponse.json({ detail: "记录不存在" }, { status: 404 }),
      ),
    );
    renderAt();
    const list = await screen.findByRole("list", { name: "待处理记录列表" });
    expect(
      await within(list).findByRole("link", { name: "打开记录「课堂录音」" }),
    ).toBeVisible();
    expect(
      within(list).getAllByRole("link", { name: /操作系统第一讲/ }),
    ).toHaveLength(1);
    expect(
      screen.queryByRole("link", { name: /已完成记录/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /处理中\s*1/ }));
    await waitFor(() =>
      expect(within(list).getAllByRole("link")).toHaveLength(1),
    );
    expect(within(list).getByText("内容处理中")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: /全部\s*3/ }));
    const pagination = await screen.findByRole("navigation", {
      name: "待处理记录分页",
    });
    fireEvent.click(within(pagination).getByRole("button", { name: "下一页" }));
    expect(await within(list).findByText("失败网页")).toBeVisible();
    expect(within(list).getByText("处理失败")).toBeVisible();
    fireEvent.click(
      within(list).getByRole("button", { name: "「失败网页」的快捷操作" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "查看原文" }));
    await waitFor(() =>
      expect(window.location.pathname).toBe("/records/failed-record"),
    );
    expect(new URLSearchParams(window.location.search).get("tab")).toBe(
      "transcript",
    );
  });

  it("保留工作台内容并保持示意条目只读", async () => {
    renderAt();

    expect(
      await screen.findByRole("heading", { name: "待办事项" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "学习趋势" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("这个分类暂无待处理事项")).toBeVisible();
    expect(screen.getAllByText("示意").length).toBeGreaterThan(0);
  });

  it("列出待确认总结并直达对应记录", async () => {
    server.use(
      http.get(TODAY_URL, () => HttpResponse.json([todo])),
      http.get(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学习记录不存在或已删除" },
          { status: 404 },
        ),
      ),
    );
    renderAt();

    const link = await screen.findByRole("link", { name: /操作系统第一讲/ });
    expect(link).toHaveAttribute("href", `/records/${RECORD_ID}`);
    expect(screen.getAllByText("操作系统").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("list", { name: "待处理记录列表" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();
  });

  it("无待办时不显示空态文案，读取失败可重试", async () => {
    renderAt();
    expect(await screen.findByText("学习趋势")).toBeInTheDocument();
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();

    cleanup();
    let calls = 0;
    server.use(
      http.get(TODAY_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json([todo]);
      }),
    );
    renderAt();
    expect(
      await screen.findByRole(
        "heading",
        { name: "今日待办暂时无法读取" },
        {
          timeout: 6_000,
        },
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    ).toBeInTheDocument();
    // 统计带并入今日页后，本用例叠加了图表渲染与重试退避，超出默认 5s。
  }, 20_000);

  it("确认总结后返回今日页，待办立即移除", async () => {
    let confirmed = false;
    let confirmCalls = 0;
    server.use(
      http.get(TODAY_URL, () => HttpResponse.json(confirmed ? [] : [todo])),
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          id: RECORD_ID,
          course_id: null,
          capture_type: "DOCUMENT_IMPORT",
          title: "操作系统第一讲",
          status: confirmed ? "COMPLETED" : "SUMMARY_READY",
          duration_ms: 0,
          summary_confirmed_at: confirmed
            ? "2026-08-23T12:05:00.000000Z"
            : null,
          created_at: "2026-08-19T08:30:00.000000Z",
          updated_at: "2026-08-23T12:00:00.000000Z",
        }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: {
            ...generatedSummary,
            status: confirmed ? "CONFIRMED" : "GENERATED",
          },
        }),
      ),
      http.post(CONFIRM_URL, async ({ request }) => {
        confirmCalls += 1;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        expect(await request.json()).toEqual({
          summary_id: generatedSummary.id,
        });
        confirmed = true;
        return HttpResponse.json({
          summary: { ...generatedSummary, status: "CONFIRMED" },
          record_status: "COMPLETED",
        });
      }),
    );
    renderAt();

    fireEvent.click(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "确认总结" }));
    expect(await screen.findByText("AI 总结 · 已确认")).toBeInTheDocument();
    expect(confirmCalls).toBe(1);

    window.history.back();
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: /操作系统第一讲/ }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();
  });
});
