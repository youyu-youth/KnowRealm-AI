// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type RecordOut = components["schemas"]["RecordOut"];

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const RECORDS_URL = `${DETAIL_URL}/records`;
const ROUTE_PATH = `/spaces/${COURSE_ID}`;

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

const recordStatuses: RecordOut["status"][] = [
  "FAILED",
  "COMPLETED",
  "SUMMARY_READY",
  "SUMMARY_PROCESSING",
  "SUMMARY_PENDING",
  "CONTENT_PROCESSING",
  "DRAFT",
  "NOTE",
];

const records: RecordOut[] = recordStatuses.map((status, index) => ({
  id: `record-${index + 1}`,
  course_id: COURSE_ID,
  capture_type: index === 0 ? "AUDIO_IMPORT" : "QUICK_NOTE",
  title: index === 7 ? "   " : `学习记录 ${index + 1}`,
  status,
  duration_ms: index === 0 ? 65_000 : 0,
  summary_confirmed_at: null,
  created_at: `2026-08-${String(19 - index).padStart(2, "0")}T08:00:00.000000Z`,
  updated_at: `2026-08-${String(19 - index).padStart(2, "0")}T08:00:00.000000Z`,
}));

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

// 详情页现在常驻拉取课程学习记录（最近记录卡 / 相关资源 / 打开课程）；
// 各用例按需覆盖，默认给空列表避免未处理请求。
beforeEach(() => {
  server.use(http.get(RECORDS_URL, () => HttpResponse.json([])));
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
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe("课程详情与编辑", () => {
  it("从列表进入详情并查看名称、场景、阶段、类型、说明与热词摘要", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([schoolCourse]),
      ),
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    );
    renderAt("/spaces");

    fireEvent.click(
      await screen.findByRole("button", { name: "打开课程 操作系统" }),
    );

    expect(
      await screen.findByRole("heading", { name: "操作系统" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("学业学习").length).toBeGreaterThan(0);
    expect(screen.getAllByText("本科").length).toBeGreaterThan(0);
    expect(screen.getAllByText("专业课").length).toBeGreaterThan(0);
    expect(screen.getByText("理解进程、内存与文件系统。")).toBeInTheDocument();
    expect(screen.getByText("暂无热词")).toBeInTheDocument();
    expect(screen.getByText("课程核心概览")).toBeInTheDocument();
  });

  it("tab 状态受 URL 校验：记录宿主可恢复、切换写回 URL、非法值回退概览", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "课程核心概览" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "概览" }));

    expect(
      await screen.findByRole("heading", { name: "课程核心概览" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=overview");

    cleanup();
    window.history.replaceState(null, "", `${ROUTE_PATH}?tab=nonsense`);
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "课程核心概览" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "还没有学习记录" }),
    ).not.toBeInTheDocument();
  });

  it("新增标签页（脑图/知识GPS/课程对话）可访问并写回 URL", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=map`);

    expect(
      await screen.findByRole("heading", { name: "课程脑图" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "知识GPS" }));

    expect(
      await screen.findByRole("heading", { name: "知识GPS · 掌握状态" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=gps");

    fireEvent.click(screen.getByRole("tab", { name: "课程对话" }));

    expect(
      await screen.findByRole("heading", { name: "课程对话" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=chat");
    expect(screen.getAllByText("示意").length).toBeGreaterThan(0);
  });

  it("知识图谱可切换力导图/树状图并提供全屏入口", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    const force = await screen.findByRole("button", { name: "力导图" });
    expect(force).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "树状图" }));

    expect(screen.getByRole("button", { name: "树状图" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "力导图" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: "全屏" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("关注为本地界面态切换且不发起请求", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    const follow = await screen.findByRole("button", { name: "关注" });
    expect(follow).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(follow);

    expect(screen.getByRole("button", { name: "已关注" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("打开课程进入最近一条学习记录", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "打开课程" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${records[0].id}`),
    );
  });

  it("没有学习记录时打开课程给出捕获引导", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "打开课程" }));

    expect(
      await screen.findByText(
        "暂无学习记录，可用顶部「速记 / 录音」创建第一条。",
      ),
    ).toBeInTheDocument();
  });

  it("学习记录加载中保持稳定状态", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, async () => {
        await delay(200);
        return HttpResponse.json([]);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(await screen.findByText("正在读取学习记录")).toHaveAttribute(
      "role",
      "status",
    );
    expect(screen.queryByText("还没有学习记录")).not.toBeInTheDocument();
  });

  it("学习记录加载失败可原地重试且不伪装为空态", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json([]);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(
      await screen.findByRole(
        "heading",
        { name: "学习记录暂时无法读取" },
        { timeout: 6_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("还没有学习记录")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(calls).toBeGreaterThanOrEqual(4);
  });

  it("真实列表呈现标题回退、采集类型、八态、创建时间和有效时长", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, ({ request }) => {
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(records);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    const list = await screen.findByRole("list", { name: "学习记录列表" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(8);
    expect(within(items[0]).getByRole("link")).toHaveAttribute(
      "href",
      `/records/${records[0].id}`,
    );
    expect(within(items[0]).getByText("音频导入")).toBeInTheDocument();
    expect(within(items[0]).getByText("1 分 5 秒")).toBeInTheDocument();
    expect(within(items[0]).getByText(/2026/)).toBeInTheDocument();
    expect(within(items[7]).getByText("未命名学习记录")).toBeInTheDocument();
    expect(
      within(items[7]).queryByText(/秒|分钟|小时/),
    ).not.toBeInTheDocument();
    for (const label of [
      "仅保存",
      "草稿",
      "内容处理中",
      "等待生成总结",
      "总结生成中",
      "总结待确认",
      "已完成",
      "处理失败",
    ]) {
      expect(within(list).getByText(label)).toBeInTheDocument();
    }
  });

  it("概览最近学习记录展示真实记录并给出查看全部入口", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(ROUTE_PATH);

    const recent = await screen.findByRole("heading", {
      name: "最近学习记录",
    });
    expect(recent).toBeInTheDocument();
    expect(await screen.findByText(`学习记录 1`)).toBeInTheDocument();

    const recentCard = recent.closest("section");
    expect(recentCard).not.toBeNull();
    fireEvent.click(
      within(recentCard as HTMLElement).getByRole("button", {
        name: /查看全部/,
      }),
    );
    await waitFor(() => expect(window.location.search).toBe("?tab=records"));
  });

  it("学习链标签页展示真实记录状态派生的流转与文字摘要", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(`${ROUTE_PATH}?tab=chain`);

    expect(
      await screen.findByRole("heading", { name: "学习链流转" }),
    ).toBeInTheDocument();
    expect(screen.getByText("8 条 · 100%")).toBeInTheDocument();
    expect(screen.getByText("5 条 · 63%")).toBeInTheDocument();
    expect(screen.getByText("4 条 · 50%")).toBeInTheDocument();
    expect(screen.getByText("1 条 · 13%")).toBeInTheDocument();
    expect(screen.getByText("未开始处理")).toBeInTheDocument();
    expect(screen.getByText("待确认")).toBeInTheDocument();
    expect(
      screen.getByText("1 条失败；记录不保存失败阶段，未计入主链。"),
    ).toBeInTheDocument();
  });

  it("学习链标签页写回 URL，空课程给出捕获引导", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("tab", { name: "学习链" }));

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=chain");
    expect(
      screen.getByText(
        "用顶部「速记 / 录音」捕获第一条，学习链会随处理进度更新。",
      ),
    ).toBeInTheDocument();
  });

  it("不存在或已软删课程显示未找到状态并提供返回知识空间路径", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ detail: "课程不存在或已删除" }, { status: 404 }),
      ),
    );
    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("heading", { name: "课程不存在或已删除" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回知识空间" })).toHaveAttribute(
      "href",
      "/spaces",
    );
  });

  it("编辑成功后详情缓存同步刷新并按契约提交 PATCH", async () => {
    let current = schoolCourse;
    let detailCalls = 0;
    let patchBody: unknown;
    let patchToken: string | null = null;
    server.use(
      http.get(DETAIL_URL, () => {
        detailCalls += 1;
        return HttpResponse.json(current);
      }),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchBody = await request.json();
        patchToken = request.headers.get("X-KnowRealm-Token");
        current = {
          ...schoolCourse,
          name: "操作系统导论",
          updated_at: "2026-08-18T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const nameField = await screen.findByRole("textbox", { name: "课程名称" });
    fireEvent.change(nameField, { target: { value: "操作系统导论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(
      await screen.findByRole("heading", { name: "操作系统导论" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "编辑课程" }),
    ).toBeInTheDocument();
    expect(detailCalls).toBeGreaterThanOrEqual(2);
    expect(patchToken).toBe(TEST_LAUNCH_TOKEN);
    expect(patchBody).toEqual({
      name: "操作系统导论",
      learning_context: "SCHOOL",
      education_stage: "UNDERGRADUATE",
      depth: null,
      course_type: "MAJOR",
      description: "理解进程、内存与文件系统。",
      hot_words: [],
    });
  });

  it("跨场景切换未选深度时保留输入、聚焦错误字段且不发请求；补选后成功保存", async () => {
    let patchCalls = 0;
    let patchBody: unknown = null;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchCalls += 1;
        patchBody = await request.json();
        return HttpResponse.json({
          ...schoolCourse,
          learning_context: "CAREER",
          education_stage: null,
          depth: "BEGINNER",
          updated_at: "2026-08-18T08:00:00.000000Z",
        });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    fireEvent.click(screen.getByRole("radio", { name: /职业技能/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("请选择学习深度")).toBeVisible();
    expect(screen.getByRole("combobox", { name: "学习深度" })).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统",
    );
    expect(patchCalls).toBe(0);

    await selectOption("学习深度", "入门");
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(patchCalls).toBe(1));
    expect(patchBody).toMatchObject({
      learning_context: "CAREER",
      education_stage: null,
      depth: "BEGINNER",
    });
    expect(
      await screen.findByRole("heading", { name: "操作系统" }),
    ).toBeInTheDocument();
  });

  it("保存失败保留输入并显示可理解错误，重试后成功", async () => {
    let current = schoolCourse;
    let patchCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(current)),
      http.patch(DETAIL_URL, () => {
        patchCalls += 1;
        if (patchCalls === 1) {
          return HttpResponse.json(
            { detail: "本地服务暂时不可用" },
            { status: 500 },
          );
        }
        current = {
          ...schoolCourse,
          name: "操作系统导论",
          updated_at: "2026-08-18T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统导论" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("本地服务暂时不可用")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统导论",
    );

    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(
      await screen.findByRole("heading", { name: "操作系统导论" }),
    ).toBeInTheDocument();
    expect(patchCalls).toBe(2);
  });

  it("API 边界 422 拒绝编辑时保留输入并显示服务端说明", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.patch(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学业场景必须选择教育阶段" },
          { status: 422 },
        ),
      ),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const nameField = await screen.findByRole("textbox", { name: "课程名称" });
    fireEvent.change(nameField, { target: { value: "操作系统导论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("学业场景必须选择教育阶段")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统导论",
    );
    expect(screen.getByRole("button", { name: "保存修改" })).toBeEnabled();
  });

  it("无效或超过 100 个热词时保留输入且不请求，合法热词按输入顺序随 PATCH 保存", async () => {
    let current = schoolCourse;
    let patchCalls = 0;
    let patchBody: unknown;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(current)),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchCalls += 1;
        patchBody = await request.json();
        current = {
          ...schoolCourse,
          hot_words: ["进程", "文件系统", "内存"],
          updated_at: "2026-08-19T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const hotWords = screen.getByRole("textbox", { name: "手动热词" });
    const tooMany = Array.from(
      { length: 101 },
      (_, index) => `热词${index}`,
    ).join("\n");
    fireEvent.change(hotWords, { target: { value: tooMany } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("最多保存 100 个热词")).toBeVisible();
    expect(hotWords).toHaveFocus();
    expect(hotWords).toHaveValue(tooMany);
    expect(patchCalls).toBe(0);

    fireEvent.change(hotWords, {
      target: { value: " 进程 \n\n 文件系统\n内存 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("热词不能为空行")).toBeVisible();
    expect(hotWords).toHaveFocus();
    expect(patchCalls).toBe(0);

    fireEvent.change(hotWords, {
      target: { value: " 进程 \n 文件系统\n内存 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(patchCalls).toBe(1));
    expect(patchBody).toMatchObject({
      hot_words: ["进程", "文件系统", "内存"],
    });
    const infoPanel = screen.getByRole("complementary", {
      name: "课程信息",
    });
    expect(within(infoPanel).getByText("进程")).toBeInTheDocument();
    expect(within(infoPanel).getByText("文件系统")).toBeInTheDocument();
    expect(within(infoPanel).getByText("内存")).toBeInTheDocument();
  });

  it("取消删除不会发请求或改变课程状态", async () => {
    let deleteCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.delete(DETAIL_URL, () => {
        deleteCalls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "删除课程" }));
    expect(screen.getByRole("heading", { name: "确认删除课程" })).toBeVisible();
    expect(screen.getByText(/当前没有恢复界面/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "确认删除课程" }),
      ).not.toBeInTheDocument(),
    );
    expect(deleteCalls).toBe(0);
    expect(screen.getByRole("heading", { name: "操作系统" })).toBeVisible();
  });

  it("删除失败可原地重试，成功后失效缓存并返回知识空间", async () => {
    let deleteCalls = 0;
    let deleteToken: string | null = null;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
      http.delete(DETAIL_URL, ({ request }) => {
        deleteCalls += 1;
        deleteToken = request.headers.get("X-KnowRealm-Token");
        if (deleteCalls === 1) {
          return HttpResponse.json(
            { detail: "数据库暂时忙，请重试" },
            { status: 500 },
          );
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "删除课程" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("数据库暂时忙，请重试")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认删除" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("还没有知识空间")).toBeVisible();
    expect(window.location.pathname).toBe("/spaces");
    expect(deleteCalls).toBe(2);
    expect(deleteToken).toBe(TEST_LAUNCH_TOKEN);
  });
});
