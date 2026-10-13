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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  overrides: Partial<components["schemas"]["InboxRecordOut"]>,
): components["schemas"]["InboxRecordOut"] => ({
  id,
  course_id: null,
  capture_type: "QUICK_NOTE",
  title: "速记标题",
  status: "NOTE",
  duration_ms: 0,
  summary_confirmed_at: null,
  created_at: "2026-08-23T10:00:00.000000Z",
  updated_at: "2026-08-23T10:00:00.000000Z",
  file_size_bytes: null,
  content_chars: null,
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

beforeEach(() => {
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/records/:id/transcript`, () =>
      HttpResponse.json({ status: "NOT_READY", transcript: null }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/records/:id/jobs`, () =>
      HttpResponse.json({ jobs: [], progress: 0 }),
    ),
  );
});

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
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "新建速记" }),
      ).not.toBeInTheDocument(),
    );
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
    fireEvent.click(await screen.findByRole("button", { name: "快速捕获" }));
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

    fireEvent.click(await screen.findByRole("button", { name: "快速捕获" }));
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
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "新建速记" }),
      ).not.toBeInTheDocument(),
    );
    expect(calls).toBe(1);
  });
});

describe("收件箱", () => {
  it("课程浏览覆盖全部活动课程，左右切换有边界且归类复用确认", async () => {
    const courses = Array.from({ length: 7 }, (_, index) => ({
      ...course,
      id: `course-${index}`,
      name: `课程 ${index + 1}`,
    }));
    const requests: object[] = [];
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([
          ...courses,
          {
            ...course,
            id: "archived-course",
            name: "归档课程",
            status: "ARCHIVED",
          },
        ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([inboxRecord(NOTE_RECORD_ID, {})]),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/inbox/bulk-classify`,
        async ({ request }) => {
          requests.push((await request.json()) as object);
          return HttpResponse.json({ results: [] });
        },
      ),
    );
    renderAt("/inbox");
    const tray = await screen.findByRole("region", { name: "归类到课程" });
    await within(tray).findByRole("button", { name: "归类所选内容到 课程 7" });
    expect(
      within(tray).queryByRole("button", { name: "归类所选内容到 归档课程" }),
    ).not.toBeInTheDocument();
    const track = within(tray).getByRole("group", { name: "归类到课程" });
    Object.defineProperties(track, {
      clientWidth: { configurable: true, value: 480 },
      scrollWidth: { configurable: true, value: 1440 },
      scrollLeft: { configurable: true, value: 0, writable: true },
    });
    const scrollBy = vi.fn((options: ScrollToOptions) => {
      track.scrollLeft = Math.min(
        960,
        Math.max(0, track.scrollLeft + (options.left ?? 0)),
      );
      fireEvent.scroll(track);
    });
    Object.defineProperty(track, "scrollBy", {
      configurable: true,
      value: scrollBy,
    });
    fireEvent.scroll(track);
    const previous = within(tray).getByRole("button", {
      name: "查看上一组课程",
    });
    const next = within(tray).getByRole("button", { name: "查看下一组课程" });
    expect(previous).toBeDisabled();
    fireEvent.click(next);
    expect(scrollBy).toHaveBeenLastCalledWith({ left: 480, behavior: "auto" });
    expect(previous).toBeEnabled();
    fireEvent.click(next);
    expect(next).toBeDisabled();
    fireEvent.click(previous);
    expect(next).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 速记标题" }));
    fireEvent.click(
      within(tray).getByRole("button", { name: "归类所选内容到 课程 7" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "归类 1 项内容" });
    expect(
      within(dialog).getByRole("combobox", { name: "所属课程" }),
    ).toHaveTextContent("课程 7");
    expect(requests).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(
      screen.getByRole("checkbox", { name: "选择 速记标题" }),
    ).toBeChecked();
  });

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
    expect(screen.getByRole("tab", { name: "速记" })).toBeVisible();
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

  it("行副标题按来源展示真实元信息（时长/大小/字数）", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(NOTE_RECORD_ID, {
            title: "SVM 速记",
            content_chars: 312,
          }),
          inboxRecord(PROCESSING_RECORD_ID, {
            capture_type: "AUDIO_IMPORT",
            title: "课堂录音",
            status: "CONTENT_PROCESSING",
            duration_ms: 5_040_000,
            file_size_bytes: 47_393_300,
          }),
          inboxRecord("44444444-4444-4444-8444-444444444444", {
            capture_type: "DOCUMENT_IMPORT",
            title: "定积分讲义.pdf",
            status: "SUMMARY_PENDING",
            file_size_bytes: 2_411_000,
          }),
        ]),
      ),
    );

    renderAt("/inbox");

    expect(await screen.findByText("312 字")).toBeVisible();
    expect(screen.getByText("时长 1 小时 24 分 · 45.2 MB")).toBeVisible();
    expect(screen.getByText("2.3 MB")).toBeVisible();
  });

  it("类型筛选写入 URL，行预览读取真实 Transcript", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(NOTE_RECORD_ID, {}),
          inboxRecord(PROCESSING_RECORD_ID, {
            capture_type: "DOCUMENT_IMPORT",
            title: "定积分讲义.pdf",
            status: "SUMMARY_PENDING",
          }),
        ]),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/records/${PROCESSING_RECORD_ID}/transcript`,
        () =>
          HttpResponse.json({
            status: "READY",
            transcript: {
              language: "zh",
              content: "定积分正文预览",
              source_version: 1,
              edited_by_user: false,
              updated_at: "2026-08-23T10:00:01.000000Z",
            },
          }),
      ),
    );

    renderAt("/inbox");
    fireEvent.click(await screen.findByRole("tab", { name: "文档" }));
    await waitFor(() =>
      expect(window.location.search).toContain("type=document"),
    );
    expect(screen.queryByText("速记标题")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "预览 定积分讲义.pdf" }),
    );
    expect(
      await screen.findByRole("heading", { name: "定积分讲义.pdf" }),
    ).toBeVisible();
    expect((await screen.findAllByText("定积分正文预览"))[0]).toBeVisible();
  });
});

describe("收件箱桌面交互", () => {
  beforeEach(() => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(NOTE_RECORD_ID, {
            title: "较早速记",
            created_at: "2026-08-22T10:00:00Z",
          }),
          inboxRecord(PROCESSING_RECORD_ID, { title: "较新速记" }),
        ]),
      ),
    );
  });

  function transfer() {
    const data = new Map<string, string>();
    return {
      types: ["application/x-knowrealm-inbox"],
      setData: (type: string, value: string) => data.set(type, value),
      getData: (type: string) => data.get(type) ?? "",
      effectAllowed: "",
      dropEffect: "",
    };
  }

  it("等待授权使用真实任务状态，宽屏列表深链接不会打开隐藏弹窗", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(PROCESSING_RECORD_ID, {
            title: "待授权录音",
            capture_type: "AUDIO_IMPORT",
            status: "CONTENT_PROCESSING",
          }),
        ]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/:id/jobs`, () =>
        HttpResponse.json({
          progress: 0.5,
          jobs: [
            {
              id: "waiting-asr",
              record_id: PROCESSING_RECORD_ID,
              job_type: "ASR",
              status: "PENDING",
              progress: 0,
              waiting_reason: "CONSENT_REQUIRED",
              attempts: 0,
              max_attempts: 3,
              error_code: null,
              retryable: false,
              sequence_no: 0,
            },
          ],
        }),
      ),
    );
    renderAt("/inbox");
    expect(await screen.findByText("等待授权")).toBeVisible();
    const oldWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1586,
    });
    try {
      cleanup();
      renderAt(`/inbox?view=list&record=${PROCESSING_RECORD_ID}`);
      await screen.findByRole("button", { name: "预览 待授权录音" });
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    } finally {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: oldWidth,
      });
    }
  });

  it("桌面与列表切换保留选择、筛选和排序，刷新 URL 可恢复", async () => {
    renderAt("/inbox?type=quick-note&sort=oldest");
    const list = await screen.findByRole("list", { name: "未归类记录列表" });
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent(
      "较早速记",
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 较早速记" }));
    fireEvent.click(screen.getByRole("tab", { name: "列表" }));
    await waitFor(() => expect(window.location.search).toContain("view=list"));
    expect(window.location.search).toContain("sort=oldest");
    expect(window.location.search).toContain("type=quick-note");
    expect(
      screen.getByRole("checkbox", { name: "选择 较早速记" }),
    ).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("tab", { name: "桌面" }));
    await waitFor(() =>
      expect(window.location.search).not.toContain("view=list"),
    );
    fireEvent.click(screen.getByRole("combobox", { name: "收件箱排序" }));
    const option = await screen.findByRole("option", {
      name: "按创建时间（最新）",
    });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() =>
      expect(
        within(
          screen.getByRole("list", { name: "未归类记录列表" }),
        ).getAllByRole("listitem")[0],
      ).toHaveTextContent("较新速记"),
    );
  });

  it("更多菜单与右键菜单进入原有确认流程，取消不提交", async () => {
    let deletes = 0;
    server.use(
      http.delete(`${TEST_SIDECAR_URL}/api/records/:id`, () => {
        deletes += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("button", { name: "更多操作：较早速记" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "删除" }));
    const dialog = await screen.findByRole("dialog", { name: "删除学习记录" });
    expect(dialog).toHaveTextContent("较早速记");
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const card = screen.getByRole("link", { name: "较早速记" }).closest("li");
    expect(card).not.toBeNull();
    fireEvent.contextMenu(card as HTMLElement, { clientX: 100, clientY: 100 });
    fireEvent.click(
      await screen.findByRole("menuitem", { name: "归类到课程" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "归类到课程" }),
    ).toHaveTextContent("较早速记");
    expect(deletes).toBe(0);
  });

  it("多选拖放先确认，取消无写入，失败项保持选择且不能重复提交", async () => {
    const calls: string[] = [];
    let removed = false;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/records/:id/classification`,
        async ({ params, request }) => {
          calls.push(String(params.id));
          expect(await request.json()).toEqual({ course_id: COURSE_ID });
          await new Promise((resolve) => setTimeout(resolve, 80));
          if (params.id === PROCESSING_RECORD_ID)
            return HttpResponse.json({ detail: "归类冲突" }, { status: 409 });
          removed = true;
          return HttpResponse.json(
            inboxRecord(NOTE_RECORD_ID, { course_id: COURSE_ID }),
          );
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          ...(removed
            ? []
            : [inboxRecord(NOTE_RECORD_ID, { title: "较早速记" })]),
          inboxRecord(PROCESSING_RECORD_ID, { title: "较新速记" }),
        ]),
      ),
    );
    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "选择 较早速记" }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 较新速记" }));
    const card = screen.getByRole("link", { name: "较早速记" }).closest("li");
    expect(card).not.toBeNull();
    const dataTransfer = transfer();
    fireEvent.dragStart(card as HTMLElement, { dataTransfer });
    const target = screen.getByRole("button", {
      name: "归类所选内容到 操作系统",
    });
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });
    const dialog = await screen.findByRole("dialog", { name: "归类 2 项内容" });
    expect(
      within(dialog).getByRole("combobox", { name: "所属课程" }),
    ).toHaveTextContent("操作系统");
    expect(calls).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    fireEvent.click(target);
    const confirm = within(
      await screen.findByRole("dialog", { name: "归类 2 项内容" }),
    ).getByRole("button", { name: "归类所选内容" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByText(/批量处理完成/)).toHaveTextContent(
      "成功 1 项，失败 1 项",
    );
    expect(calls).toHaveLength(2);
    expect(
      screen.getByRole("checkbox", { name: "选择 较新速记" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("外部拖入与包含处理中记录的多选拖动均不会提交", async () => {
    let calls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json([
          inboxRecord(NOTE_RECORD_ID, { title: "较早速记" }),
          inboxRecord(PROCESSING_RECORD_ID, {
            title: "处理中音频",
            status: "CONTENT_PROCESSING",
            capture_type: "AUDIO_IMPORT",
          }),
        ]),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/records/:id/classification`, () => {
        calls += 1;
        return HttpResponse.json({});
      }),
    );
    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "选择 较早速记" }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 处理中音频" }));
    const card = screen.getByRole("link", { name: "较早速记" }).closest("li");
    expect(card).not.toBeNull();
    const dataTransfer = transfer();
    expect(fireEvent.dragStart(card as HTMLElement, { dataTransfer })).toBe(
      false,
    );
    fireEvent.drop(
      screen.getByRole("button", { name: "归类所选内容到 操作系统" }),
      { dataTransfer },
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls).toBe(0);
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

  it("批量归类部分失败时只保留失败项的选择", async () => {
    const failedId = PROCESSING_RECORD_ID;
    let successfulRemoved = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([course]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/inbox`, () =>
        HttpResponse.json(
          successfulRemoved
            ? [inboxRecord(failedId, { title: "归类失败记录" })]
            : [
                inboxRecord(NOTE_RECORD_ID, {}),
                inboxRecord(failedId, { title: "归类失败记录" }),
              ],
        ),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/records/:id/classification`,
        ({ params }) => {
          if (params.id === failedId) {
            return HttpResponse.json({ detail: "归类冲突" }, { status: 409 });
          }
          successfulRemoved = true;
          return HttpResponse.json(
            inboxRecord(NOTE_RECORD_ID, { course_id: COURSE_ID }),
          );
        },
      ),
    );

    renderAt("/inbox");
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "选择 速记标题" }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: "选择 归类失败记录" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "归类课程" }));
    await selectCourse("所属课程");
    fireEvent.click(screen.getByRole("button", { name: "归类所选内容" }));

    expect(await screen.findByText(/批量处理完成/)).toHaveTextContent(
      "成功 1 项，失败 1 项",
    );
    expect(screen.queryByText("速记标题")).not.toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "选择 归类失败记录" }),
    ).toHaveAttribute("aria-checked", "true");
  });

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
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "归类到课程" }),
      ).not.toBeInTheDocument(),
    );
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
