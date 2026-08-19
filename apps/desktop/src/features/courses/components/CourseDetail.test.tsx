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
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
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

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

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

    fireEvent.click(await screen.findByRole("button", { name: "操作系统" }));

    expect(
      await screen.findByRole("heading", { name: "操作系统" }),
    ).toBeInTheDocument();
    expect(screen.getByText("学业学习")).toBeInTheDocument();
    expect(screen.getByText("本科")).toBeInTheDocument();
    expect(screen.getByText("专业课")).toBeInTheDocument();
    expect(screen.getByText("理解进程、内存与文件系统。")).toBeInTheDocument();
    expect(screen.getByText("暂无热词")).toBeInTheDocument();
  });

  it("tab 状态受 URL 校验：记录宿主可恢复、切换写回 URL、非法值回退概览", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(await screen.findByText("学习记录尚未接入")).toBeInTheDocument();
    expect(screen.queryByText("课程信息")).not.toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "概览" }));

    expect(await screen.findByText("课程信息")).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=overview");

    cleanup();
    window.history.replaceState(null, "", `${ROUTE_PATH}?tab=nonsense`);
    render(<App />);

    expect(await screen.findByText("课程信息")).toBeInTheDocument();
    expect(screen.queryByText("学习记录尚未接入")).not.toBeInTheDocument();
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
    await selectOption("学习场景", "职业技能");
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

    expect(await screen.findByText("进程 · 文件系统 · 内存")).toBeVisible();
    expect(patchCalls).toBe(1);
    expect(patchBody).toMatchObject({
      hot_words: ["进程", "文件系统", "内存"],
    });
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
