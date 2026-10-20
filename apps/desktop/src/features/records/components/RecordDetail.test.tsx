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
import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { recordApi } from "@/features/records/api/records";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const COURSE_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const COURSE_RECORDS_URL = `${COURSE_URL}/records`;
const ROUTE_PATH = `/records/${RECORD_ID}`;
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const JOBS_URL = `${DETAIL_URL}/jobs`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const REVIEW_MATERIAL_URL = `${DETAIL_URL}/review-material`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const LLM_CONSENT_URL = `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/llm`;

function jobsResponse(
  job: Partial<components["schemas"]["ProcessingJobOut"]> = {},
) {
  const completeJob: components["schemas"]["ProcessingJobOut"] = {
    id: JOB_ID,
    record_id: RECORD_ID,
    job_type: "DOCUMENT_PARSE",
    status: "FAILED",
    progress: 0,
    attempts: 1,
    max_attempts: 3,
    error_code: "TEMPORARY_IO",
    retryable: true,
    waiting_reason: null,
    ...job,
    sequence_no: job.sequence_no ?? 0,
    source_name: job.source_name ?? null,
  };
  return { jobs: [completeJob], progress: completeJob.progress };
}

const record: RecordOut = {
  id: RECORD_ID,
  course_id: COURSE_ID,
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "SUMMARY_PENDING",
  duration_ms: 65_000,
  summary_confirmed_at: null,
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-19T08:30:00.000000Z",
};

const course: components["schemas"]["CourseDetailOut"] = {
  id: COURSE_ID,
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: null,
  status: "ACTIVE",
  hot_words: [],
  created_at: "2026-08-19T08:00:00.000000Z",
  updated_at: "2026-08-19T08:00:00.000000Z",
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());
window.Element.prototype.scrollIntoView = vi.fn();

beforeEach(() => {
  server.use(
    http.get(SUMMARY_URL, () =>
      HttpResponse.json({
        action_required: "GENERATE",
        active_job_id: null,
        blocked_reason: null,
        summary: null,
      }),
    ),
    http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
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

describe("学习记录详情", () => {
  it("可直接打开并在刷新后从详情接口恢复真实元数据", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, ({ request }) => {
        calls += 1;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(record);
      }),
    );

    renderAt();
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();
    expect(screen.getByText("音频导入")).toBeInTheDocument();
    expect(screen.getByText("等待生成总结")).toBeInTheDocument();
    expect(screen.getByText("1 分 5 秒")).toBeInTheDocument();

    cleanup();
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("加载失败可重试，404 则显示不存在状态", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json(record);
      }),
    );
    renderAt();

    expect(
      await screen.findByRole(
        "heading",
        { name: "学习记录暂时无法读取" },
        { timeout: 6_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("学习记录暂时无法读取");
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学习记录不存在或已删除" },
          { status: 404 },
        ),
      ),
    );
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "学习记录不存在或已删除" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "学习记录不存在或已删除",
    );
    expect(screen.getByRole("link", { name: "返回知识空间" })).toHaveAttribute(
      "href",
      "/spaces",
    );
  });

  it("加载期间不闪现空态，普通详情默认 Summary 且仅未接入资产禁用", async () => {
    server.use(
      http.get(DETAIL_URL, async () => {
        await delay(200);
        return HttpResponse.json(record);
      }),
      http.get(`${DETAIL_URL}/transcript`, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 0 })),
    );
    renderAt();

    expect(await screen.findByText("正在读取学习记录详情")).toHaveAttribute(
      "role",
      "status",
    );
    expect(screen.queryByText("还没有生成总结")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "还没有生成总结" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Transcript" })).toBeEnabled();
    expect(screen.getByRole("tab", { name: "知识点" })).toBeEnabled();
    for (const label of ["习题", "复习", "Todo", "Ask AI"]) {
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "tabindex",
        "-1",
      );
    }
    expect(
      screen.getByText("确认总结后解锁习题、复习与 Todo；Ask AI 尚未接入"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/示例总结/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Transcript" }));
    expect(await screen.findByText("正文尚未生成")).toBeVisible();
  });

  it("完成记录可从 review 路由生成并轮询进行中态", async () => {
    let active = false;
    let submits = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          status: "COMPLETED",
          summary_confirmed_at: "2026-09-06T12:00:00.000000Z",
        }),
      ),
      http.get(REVIEW_MATERIAL_URL, () =>
        HttpResponse.json({
          review_material: null,
          action_required: active ? "NONE" : "GENERATE",
          blocked_reason: null,
          active_job_id: active ? JOB_ID : null,
        }),
      ),
      http.post(`${DETAIL_URL}/review-material-jobs`, () => {
        submits += 1;
        if (submits === 1) {
          return HttpResponse.json(
            { detail: "Provider 暂时不可用" },
            { status: 500 },
          );
        }
        active = true;
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );

    renderAt(`${ROUTE_PATH}?tab=review`);
    expect(await screen.findByRole("tab", { name: "复习" })).toBeEnabled();
    fireEvent.click(
      await screen.findByRole("button", { name: "生成复习资料" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Provider 暂时不可用",
    );
    fireEvent.click(screen.getByRole("button", { name: "生成复习资料" }));
    expect(await screen.findByText("正在生成复习资料")).toBeVisible();
    expect(submits).toBe(2);
  });

  it("review 路由按考前速记、重点清单和大纲树显示生成结果", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          status: "COMPLETED",
          summary_confirmed_at: "2026-09-06T12:00:00.000000Z",
        }),
      ),
      http.get(REVIEW_MATERIAL_URL, () =>
        HttpResponse.json({
          review_material: {
            id: "55555555-5555-4555-8555-555555555555",
            record_id: RECORD_ID,
            version_no: 1,
            transcript_source_version: 1,
            generated_from_summary_id: "66666666-6666-4666-8666-666666666666",
            quick_review: "## 调度速记\n\n时间片轮转兼顾公平性。",
            key_list: ["理解调度目标", "比较调度算法"],
            mind_map_markdown:
              "- 根级重点\n# 进程调度\n## 基础\n- 调度目标\n## 算法\n- 时间片轮转",
            status: "GENERATED",
            model: "qwen-plus",
            prompt_version: "review_v1",
            user_feedback: null,
            created_at: "2026-09-06T12:00:00.000000Z",
          },
          action_required: "NONE",
          blocked_reason: null,
          active_job_id: null,
        }),
      ),
    );

    renderAt(`${ROUTE_PATH}?tab=review`);

    expect(
      await screen.findByRole("heading", { name: "考前速记" }),
    ).toBeVisible();
    expect(screen.getByText("时间片轮转兼顾公平性。")).toBeVisible();
    expect(screen.getByRole("heading", { name: "重点清单" })).toBeVisible();
    expect(screen.getByText("比较调度算法")).toBeVisible();
    const outline = screen
      .getByRole("heading", { name: "大纲树" })
      .closest("section")!;
    expect(outline).toBeVisible();
    expect(screen.getByText("根级重点")).toBeVisible();
    const branches = within(outline).getAllByRole("group");
    expect(branches).toHaveLength(4);
    expect(branches.every((branch) => branch.hasAttribute("open"))).toBe(true);
  });

  it("复习资料授权失败时保留操作入口并显示服务端错误", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          status: "COMPLETED",
          summary_confirmed_at: "2026-09-06T12:00:00.000000Z",
        }),
      ),
      http.get(REVIEW_MATERIAL_URL, () =>
        HttpResponse.json({
          review_material: null,
          action_required: "GRANT_CONSENT",
          blocked_reason: null,
          active_job_id: null,
        }),
      ),
      http.post(LLM_CONSENT_URL, () =>
        HttpResponse.json({ detail: "授权写入失败" }, { status: 500 }),
      ),
    );

    renderAt(`${ROUTE_PATH}?tab=review`);
    fireEvent.click(
      await screen.findByRole("button", { name: "同意并继续生成" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("授权写入失败");
    expect(
      screen.getByRole("button", { name: "同意并继续生成" }),
    ).toBeEnabled();
  });
});

describe("学习记录详情生命周期与接线", () => {
  it("返回路径由真实课程归属决定，空课程归属返回收件箱", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(record)));
    renderAt();

    expect(
      await screen.findByRole("link", { name: "返回课程学习记录" }),
    ).toHaveAttribute("href", `/spaces/${COURSE_ID}?tab=records`);

    cleanup();
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, course_id: null, title: "   " }),
      ),
    );
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "未命名学习记录" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除学习记录" })).toBeVisible();
    expect(
      await screen.findByRole("link", { name: "返回收件箱" }),
    ).toHaveAttribute("href", "/inbox");
  });

  it("SSE 只触发 REST 失效刷新，并携带启动令牌", async () => {
    let streamCalls = 0;
    server.use(
      http.get(`${DETAIL_URL}/events`, ({ request }) => {
        streamCalls += 1;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        expect(request.headers.get("Accept")).toBe("text/event-stream");
        return new HttpResponse(
          `event: invalidate\ndata: {"record_id":"${RECORD_ID}"}\n\n`,
          {
            headers: { "Content-Type": "text/event-stream" },
          },
        );
      }),
    );
    const onOpen = vi.fn();
    const onInvalidate = vi.fn();

    await expect(
      recordApi.subscribe(RECORD_ID, undefined, onOpen, onInvalidate),
    ).rejects.toThrow("Record 事件流已断开");

    expect(streamCalls).toBe(1);
    expect(onOpen).toHaveBeenCalledOnce();
    expect(onInvalidate).toHaveBeenCalledOnce();
  });

  it("取消或关闭确认对话框不发删除请求，并将焦点恢复到删除入口", async () => {
    let deleteCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.delete(DETAIL_URL, () => {
        deleteCalls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt();

    const trigger = await screen.findByRole("button", { name: "删除学习记录" });
    fireEvent.click(trigger);
    expect(
      screen.getByRole("heading", { name: "确认删除学习记录" }),
    ).toBeVisible();
    expect(screen.getByText(/无法恢复/)).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(trigger).toHaveFocus());
    expect(deleteCalls).toBe(0);

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "确认删除学习记录" }),
      ).not.toBeInTheDocument(),
    );
    expect(deleteCalls).toBe(0);
  });

  it("处理中删除失败后恢复轮询，再次确认时停止轮询并清理导航", async () => {
    let jobCalls = 0;
    let deleteCalls = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          capture_type: "DOCUMENT_IMPORT",
          status: "CONTENT_PROCESSING",
        }),
      ),
      http.get(JOBS_URL, () => {
        jobCalls += 1;
        return HttpResponse.json(
          jobsResponse({
            status: "RUNNING",
            error_code: null,
            retryable: false,
          }),
        );
      }),
      http.get(`${DETAIL_URL}/transcript`, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
      http.get(`${DETAIL_URL}/events`, () =>
        HttpResponse.json({ detail: "stream unavailable" }, { status: 503 }),
      ),
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(COURSE_RECORDS_URL, () => HttpResponse.json([])),
      http.delete(DETAIL_URL, async () => {
        deleteCalls += 1;
        if (deleteCalls === 1) {
          return HttpResponse.json(
            { detail: "数据库暂时忙，请重试" },
            { status: 500 },
          );
        }
        await delay(2_300);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript`);

    expect(await screen.findByText("正在生成 Transcript")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "删除学习记录" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect(await screen.findByText("数据库暂时忙，请重试")).toBeVisible();

    const callsAfterFailure = jobCalls;
    await new Promise((resolve) => window.setTimeout(resolve, 2_100));
    expect(jobCalls).toBeGreaterThan(callsAfterFailure);

    const confirm = screen.getByRole("button", { name: "确认删除" });
    fireEvent.click(confirm);
    await waitFor(() => expect(confirm).toBeDisabled());
    const callsWhileDeleting = jobCalls;
    await new Promise((resolve) => window.setTimeout(resolve, 2_100));
    expect(jobCalls).toBe(callsWhileDeleting);

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeVisible();
    expect(window.location.pathname).toBe(`/spaces/${COURSE_ID}`);
    expect(window.location.search).toBe("?tab=records");
  }, 10_000);

  it("删除失败保留详情并可重试，成功后刷新课程列表缓存并导航", async () => {
    let deleted = false;
    let deleteCalls = 0;
    let listCalls = 0;
    let deleteToken: string | null = null;
    const failedRecord = { ...record, status: "FAILED" as const };
    server.use(
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(COURSE_RECORDS_URL, () => {
        listCalls += 1;
        return HttpResponse.json(deleted ? [] : [failedRecord]);
      }),
      http.get(DETAIL_URL, () =>
        deleted
          ? HttpResponse.json(
              { detail: "学习记录不存在或已删除" },
              { status: 404 },
            )
          : HttpResponse.json(failedRecord),
      ),
      http.delete(DETAIL_URL, async ({ request }) => {
        deleteCalls += 1;
        deleteToken = request.headers.get("X-KnowRealm-Token");
        if (deleteCalls === 1) {
          await delay(100);
          return HttpResponse.json(
            { detail: "数据库暂时忙，请重试" },
            { status: 500 },
          );
        }
        await delay(100);
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(`/spaces/${COURSE_ID}?tab=records`);

    fireEvent.click(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "删除学习记录" }),
    );
    const confirm = screen.getByRole("button", { name: "确认删除" });
    fireEvent.click(confirm);
    await waitFor(() => expect(confirm).toBeDisabled());
    fireEvent.click(confirm);

    expect(deleteCalls).toBe(1);
    expect(await screen.findByText("数据库暂时忙，请重试")).toBeVisible();
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(window.location.pathname).toBe(`/records/${RECORD_ID}`);

    const retry = screen.getByRole("button", { name: "确认删除" });
    fireEvent.click(retry);
    await waitFor(() => expect(retry).toBeDisabled());
    fireEvent.click(retry);
    expect(deleteCalls).toBe(2);

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeVisible();
    expect(window.location.pathname).toBe(`/spaces/${COURSE_ID}`);
    expect(window.location.search).toBe("?tab=records");
    expect(deleteCalls).toBe(2);
    expect(deleteToken).toBe(TEST_LAUNCH_TOKEN);
    expect(listCalls).toBe(2);
  });
});
