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
const NOTE_RECORD_ID = "22222222-2222-4222-8222-222222222222";
const PROCESSING_RECORD_ID = "33333333-3333-4333-8333-333333333333";

const course: components["schemas"]["CourseOut"] = {
  id: COURSE_ID,
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: null,
  status: "ACTIVE",
  created_at: "2026-08-20T08:00:00.000000Z",
  updated_at: "2026-08-20T08:00:00.000000Z",
};

const inboxRecord = (
  id: string,
  overrides: Partial<components["schemas"]["RecordOut"]>,
): components["schemas"]["RecordOut"] => ({
  id,
  course_id: null,
  capture_type: "QUICK_NOTE",
  title: "速记标题",
  status: "NOTE",
  duration_ms: 0,
  summary_confirmed_at: null,
  created_at: "2026-08-23T10:00:00.000000Z",
  updated_at: "2026-08-23T10:00:00.000000Z",
  ...overrides,
});

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

function mockRecordDetail(recordId: string, course_id: string | null) {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
      HttpResponse.json({
        id: recordId,
        course_id,
        capture_type: "QUICK_NOTE",
        title: "速记标题",
        status: "NOTE",
        duration_ms: 0,
        summary_confirmed_at: null,
        created_at: "2026-08-23T10:00:00.000000Z",
        updated_at: "2026-08-23T10:00:00.000000Z",
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
          content: "速记正文\n\n第二段",
          source_version: 1,
          edited_by_user: false,
          updated_at: "2026-08-23T10:00:01.000000Z",
        },
      }),
    ),
  );
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("文本捕获", () => {
  it("速记入口创建无课程 NOTE，成功后留在当前页面并给出可访问反馈", async () => {
    const bodies: object[] = [];
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/text-captures`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          return HttpResponse.json({
            record_id: NOTE_RECORD_ID,
            summary_job_id: null,
          });
        },
      ),
    );

    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "新建速记" }));

    expect(
      await screen.findByRole("heading", { name: "新建速记" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("combobox", { name: "所属课程" }),
    ).not.toBeInTheDocument();
    expect(document.activeElement?.id).toBe("text-capture-body");
    const submit = screen.getByRole("button", { name: "保存" });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText("正文"), {
      target: { value: "速记正文\n\n第二段" },
    });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    expect(await screen.findByRole("status", { name: "" })).toHaveTextContent(
      "已保存到本地收件箱",
    );
    expect(
      screen.queryByRole("heading", { name: "新建速记" }),
    ).not.toBeInTheDocument();
    expect(bodies).toEqual([
      { capture_type: "QUICK_NOTE", content: "速记正文\n\n第二段" },
    ]);
    expect(window.location.pathname).toBe("/");
  });

  it("粘贴入口默认暂不归类，选择课程后进入 Record 总结页", async () => {
    let courseSelected = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/text-captures`,
        async ({ request }) => {
          const body = (await request.json()) as { course_id: string | null };
          courseSelected = body.course_id !== null;
          return HttpResponse.json({
            record_id: NOTE_RECORD_ID,
            summary_job_id: courseSelected ? "job-1" : null,
          });
        },
      ),
    );
    mockRecordDetail(NOTE_RECORD_ID, courseSelected ? COURSE_ID : null);

    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "粘贴文本" }));

    expect(
      await screen.findByRole("heading", { name: "粘贴文本" }),
    ).toBeVisible();
    const courseSelect = screen.getByRole("combobox", { name: "所属课程" });
    expect(courseSelect).toHaveTextContent("暂不归类");

    fireEvent.change(screen.getByLabelText("正文"), {
      target: { value: "未归类粘贴正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("status", { name: "" })).toHaveTextContent(
      "已保存到本地收件箱",
    );
    expect(window.location.pathname).toBe("/");

    fireEvent.click(screen.getByRole("button", { name: "粘贴文本" }));
    const reopened = screen.getByRole("combobox", { name: "所属课程" });
    await waitFor(() => expect(reopened).toBeEnabled());
    expect(reopened).toHaveTextContent("暂不归类");
    fireEvent.click(reopened);
    const option = await screen.findByRole("option", { name: "操作系统" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    fireEvent.change(screen.getByLabelText("正文"), {
      target: { value: "已归类粘贴正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${NOTE_RECORD_ID}`),
    );
    expect(window.location.search).toBe("");
  });

  it("空白正文与超过 1 MiB 的正文都不能提交", async () => {
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "新建速记" }));
    const submit = screen.getByRole("button", { name: "保存" });
    const body = screen.getByLabelText("正文");

    fireEvent.change(body, { target: { value: " \n\t " } });
    expect(submit).toBeDisabled();

    fireEvent.change(body, {
      target: { value: "a".repeat(1024 * 1024 + 1) },
    });
    await waitFor(() =>
      expect(
        screen.getByText("正文超过 1 MiB，请改用 TXT 或 MD 文档导入。"),
      ).toBeVisible(),
    );
    expect(submit).toBeDisabled();
  }, 15_000);

  it("保存失败保留正文，提交中防重复，取消不产生业务副作用", async () => {
    let calls = 0;
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/text-captures`, async () => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 300));
        return HttpResponse.json(
          { detail: "EMPTY_TEXT：正文不能为空" },
          { status: 422 },
        );
      }),
    );

    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "新建速记" }));
    fireEvent.change(screen.getByLabelText("正文"), {
      target: { value: "会失败的正文" },
    });
    const submit = screen.getByRole("button", { name: "保存" });
    fireEvent.click(submit);

    await waitFor(() =>
      expect(screen.getByLabelText("正在保存")).toBeInTheDocument(),
    );
    expect(submit).toBeDisabled();
    fireEvent.click(submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "EMPTY_TEXT：正文不能为空",
    );
    expect(calls).toBe(1);
    expect(screen.getByLabelText("正文")).toHaveValue("会失败的正文");

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(
      screen.queryByRole("heading", { name: "新建速记" }),
    ).not.toBeInTheDocument();
    expect(calls).toBe(1);
  });
});

describe("收件箱", () => {
  it("空态如实展示，没有示例数据", async () => {
    renderAt("/inbox");

    expect(
      await screen.findByRole("heading", { name: "收件箱是空的" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("加载失败展示错误与重试入口", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json({ detail: "服务暂不可用" }, { status: 500 }),
      ),
    );

    renderAt("/inbox");

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("收件箱暂时无法读取");
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  });

  it("列出未归类记录，行内导航进入 Transcript，无课程详情返回收件箱", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([inboxRecord(NOTE_RECORD_ID, {})]),
      ),
    );
    mockRecordDetail(NOTE_RECORD_ID, null);

    renderAt("/inbox");

    const row = await screen.findByRole("link", { name: /速记标题/ });
    expect(screen.getByText("速记")).toBeVisible();
    expect(screen.getByText("仅保存")).toBeVisible();
    fireEvent.click(row);

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${NOTE_RECORD_ID}`),
    );
    expect(window.location.search).toBe("?tab=transcript");
    expect(
      await screen.findByRole("link", { name: "返回收件箱" }),
    ).toHaveAttribute("href", "/inbox");
  });

  it("存在处理中记录时每 2 秒轮询，终态后停止", async () => {
    let calls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () => {
        calls += 1;
        return HttpResponse.json([
          inboxRecord(PROCESSING_RECORD_ID, {
            capture_type: "DOCUMENT_IMPORT",
            title: "解析中的文档",
            status: calls >= 2 ? "SUMMARY_PENDING" : "CONTENT_PROCESSING",
          }),
        ]);
      }),
    );

    renderAt("/inbox");

    expect(await screen.findByText("解析中的文档")).toBeVisible();
    expect(screen.getByText("内容处理中")).toBeVisible();
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2), {
      timeout: 5_000,
    });
    await waitFor(() => expect(screen.getByText("等待生成总结")).toBeVisible());
    const settled = calls;
    await new Promise((resolve) => setTimeout(resolve, 2_600));
    expect(calls).toBe(settled);
  }, 15_000);

  it("删除成功后行立即移除", async () => {
    let deleted = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json(deleted ? [] : [inboxRecord(NOTE_RECORD_ID, {})]),
      ),
      http.delete(`${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderAt("/inbox");

    fireEvent.click(
      await screen.findByRole("button", { name: "删除 速记标题" }),
    );
    expect(
      await screen.findByRole("heading", { name: "删除学习记录" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() =>
      expect(screen.queryByText("速记标题")).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByRole("heading", { name: "收件箱是空的" }),
    ).toBeVisible();
  });
});

describe("收件箱归类与升级", () => {
  const llmProviderMissing = http.get(
    `${TEST_SIDECAR_URL}/api/settings/providers/llm`,
    () =>
      HttpResponse.json({
        provider: {
          base_url: "https://example.com/v1",
          model: "qwen-plus",
          api_key_hint: null,
          has_api_key: false,
        },
      }),
  );

  async function selectCourse(label: string) {
    const select = screen.getByRole("combobox", { name: label });
    await waitFor(() => expect(select).toBeEnabled());
    fireEvent.click(select);
    const option = await screen.findByRole("option", { name: "操作系统" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    return select;
  }

  it("NOTE 行提供归类与升级，CONTENT_PROCESSING 行不显示不可执行动作", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(NOTE_RECORD_ID, {}),
          inboxRecord(PROCESSING_RECORD_ID, {
            capture_type: "DOCUMENT_IMPORT",
            title: "解析中文档",
            status: "CONTENT_PROCESSING",
          }),
        ]),
      ),
    );

    renderAt("/inbox");

    expect(
      await screen.findByRole("button", { name: "归类 速记标题" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "升级 速记标题" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "归类 解析中文档" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "升级 解析中文档" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "删除 解析中文档" }),
    ).toBeVisible();
  });

  it("纯归类成功后留在收件箱，行消失并显示已归类到课程", async () => {
    const bodies: object[] = [];
    let classified = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json(classified ? [] : [inboxRecord(NOTE_RECORD_ID, {})]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/classification`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          classified = true;
          return HttpResponse.json(
            inboxRecord(NOTE_RECORD_ID, { course_id: COURSE_ID }),
          );
        },
      ),
    );

    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "归类 速记标题" }),
    );
    await selectCourse("所属课程");
    fireEvent.click(screen.getByRole("button", { name: "归类" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "已归类到 操作系统",
    );
    expect(window.location.pathname).toBe("/inbox");
    expect(screen.queryByText("速记标题")).not.toBeInTheDocument();
    expect(bodies).toEqual([{ course_id: COURSE_ID }]);
  });

  it("归类冲突时对话框保留课程选择并显示错误，Escape 取消不产生请求", async () => {
    let calls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([inboxRecord(NOTE_RECORD_ID, {})]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/classification`,
        () => {
          calls += 1;
          return HttpResponse.json(
            { detail: "学习记录已归到其他课程，本版本不支持重新归类" },
            { status: 409 },
          );
        },
      ),
    );

    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "归类 速记标题" }),
    );
    const select = await selectCourse("所属课程");
    fireEvent.click(screen.getByRole("button", { name: "归类" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "学习记录已归到其他课程",
    );
    expect(select).toHaveTextContent("操作系统");

    fireEvent.keyDown(document.activeElement ?? document.body, {
      key: "Escape",
    });
    expect(
      screen.queryByRole("heading", { name: "归类到课程" }),
    ).not.toBeInTheDocument();
    expect(calls).toBe(1);
  });

  it("升级成功后导航到 Record 总结页，未入队也不影响导航", async () => {
    const bodies: object[] = [];
    server.use(
      llmProviderMissing,
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([inboxRecord(NOTE_RECORD_ID, {})]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/upgrade`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          return HttpResponse.json({
            record: inboxRecord(NOTE_RECORD_ID, {
              course_id: COURSE_ID,
              status: "SUMMARY_PENDING",
            }),
            summary_job_id: null,
          });
        },
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/summary`,
        () =>
          HttpResponse.json({
            summary: null,
            action_required: "CONFIGURE_PROVIDER",
          }),
      ),
    );
    mockRecordDetail(NOTE_RECORD_ID, COURSE_ID);

    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "升级 速记标题" }),
    );
    await selectCourse("所属课程");
    fireEvent.click(screen.getByRole("button", { name: "升级" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${NOTE_RECORD_ID}`),
    );
    expect(window.location.search).toBe("");
    expect(bodies).toEqual([{ course_id: COURSE_ID }]);
    expect(
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
  });

  it("无课程 Summary 页显示请先归类并升级并提供课程选择器", async () => {
    const bodies: object[] = [];
    let upgraded = false;
    server.use(
      llmProviderMissing,
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}`, () =>
        HttpResponse.json({
          ...inboxRecord(NOTE_RECORD_ID, {}),
          ...(upgraded
            ? { course_id: COURSE_ID, status: "SUMMARY_PENDING" }
            : {}),
        }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/summary`,
        () =>
          HttpResponse.json(
            upgraded
              ? { summary: null, action_required: "CONFIGURE_PROVIDER" }
              : {
                  summary: null,
                  action_required: "NONE",
                  blocked_reason: "COURSE_REQUIRED",
                },
          ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/upgrade`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          upgraded = true;
          return HttpResponse.json({
            record: inboxRecord(NOTE_RECORD_ID, {
              course_id: COURSE_ID,
              status: "SUMMARY_PENDING",
            }),
            summary_job_id: null,
          });
        },
      ),
    );

    renderAt(`/records/${NOTE_RECORD_ID}`);

    expect(
      await screen.findByRole("heading", { name: "当前无法生成总结" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "请先归类并升级：选择一门进行中的课程后，才能进入总结流程。",
      ),
    ).toBeVisible();
    await selectCourse("所属课程");
    fireEvent.click(screen.getByRole("button", { name: "归类并升级" }));

    expect(
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
    expect(bodies).toEqual([{ course_id: COURSE_ID }]);
    expect(screen.getByText("等待生成总结")).toBeVisible();
  });

  it("已归类 NOTE 的 Summary 页提供不重复选课的升级入口", async () => {
    const bodies: object[] = [];
    let upgraded = false;
    server.use(
      llmProviderMissing,
      http.get(`${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}`, () =>
        HttpResponse.json(
          inboxRecord(NOTE_RECORD_ID, {
            course_id: COURSE_ID,
            ...(upgraded ? { status: "SUMMARY_PENDING" } : {}),
          }),
        ),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/summary`,
        () =>
          HttpResponse.json(
            upgraded
              ? {
                  summary: null,
                  action_required: "NONE",
                  active_job_id: "job-9",
                }
              : { summary: null, action_required: "GENERATE" },
          ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/upgrade`,
        async ({ request }) => {
          bodies.push((await request.json()) as object);
          upgraded = true;
          return HttpResponse.json({
            record: inboxRecord(NOTE_RECORD_ID, {
              course_id: COURSE_ID,
              status: "SUMMARY_PENDING",
            }),
            summary_job_id: "job-9",
          });
        },
      ),
    );

    renderAt(`/records/${NOTE_RECORD_ID}`);

    const upgrade = await screen.findByRole("button", {
      name: "升级进入总结流程",
    });
    expect(
      screen.queryByRole("combobox", { name: "所属课程" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "生成总结" }),
    ).not.toBeInTheDocument();
    fireEvent.click(upgrade);

    expect(await screen.findByText("正在生成总结")).toBeVisible();
    expect(bodies).toEqual([{ course_id: null }]);
  });

  it("课程加载失败或没有 ACTIVE 课程时显示诚实状态且不能提交", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json({ detail: "服务暂不可用" }, { status: 500 }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([inboxRecord(NOTE_RECORD_ID, {})]),
      ),
    );

    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "归类 速记标题" }),
    );
    const select = await screen.findByRole("combobox", {
      name: "所属课程",
    });
    await waitFor(() => expect(select).toBeDisabled());
    expect(
      await screen.findByText("课程暂时无法读取，请关闭后重试。", undefined, {
        timeout: 8_000,
      }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "归类" })).toBeDisabled();

    cleanup();
    window.history.replaceState(null, "", "/inbox");
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    );
    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "归类 速记标题" }),
    );
    const emptySelect = await screen.findByRole("combobox", {
      name: "所属课程",
    });
    await waitFor(() => expect(emptySelect).toBeDisabled());
    expect(
      await screen.findByText(
        "暂无进行中的课程，请先在知识空间创建或恢复课程。",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "归类" })).toBeDisabled();
  });

  it("编辑 NOTE Transcript 后记录仍为 NOTE，标题不变", async () => {
    const patches: object[] = [];
    server.use(
      llmProviderMissing,
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/summary`,
        () =>
          HttpResponse.json({
            summary: null,
            action_required: "NONE",
            blocked_reason: "COURSE_REQUIRED",
          }),
      ),
      http.patch(
        `${TEST_SIDECAR_URL}/api/records/${NOTE_RECORD_ID}/transcript`,
        async ({ request }) => {
          const body = (await request.json()) as {
            content: string;
            expected_source_version: number;
          };
          patches.push(body);
          return HttpResponse.json({
            language: "und",
            content: body.content,
            source_version: body.expected_source_version + 1,
            edited_by_user: true,
            updated_at: "2026-08-23T10:05:00.000000Z",
          });
        },
      ),
    );
    mockRecordDetail(NOTE_RECORD_ID, null);

    renderAt(`/records/${NOTE_RECORD_ID}`);
    fireEvent.click(await screen.findByRole("tab", { name: "Transcript" }));

    fireEvent.click(await screen.findByRole("button", { name: "编辑正文" }));
    const editor = screen.getByLabelText("Transcript 正文编辑器");
    fireEvent.change(editor, { target: { value: "修改后的速记正文" } });
    fireEvent.click(screen.getByRole("button", { name: "保存正文" }));

    await waitFor(() =>
      expect(screen.getByText("修改后的速记正文")).toBeVisible(),
    );
    expect(screen.getByText("仅保存")).toBeVisible();
    expect(screen.getByRole("heading", { name: "速记标题" })).toBeVisible();
    expect(patches).toEqual([
      { content: "修改后的速记正文", expected_source_version: 1 },
    ]);
  });
});
