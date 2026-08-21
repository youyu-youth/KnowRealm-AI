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
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
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
const JOB_URL = `${TEST_SIDECAR_URL}/api/processing-jobs/${JOB_ID}`;
const JOB_RETRY_URL = `${JOB_URL}/retries`;

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
    for (const label of ["Highlights", "Notes", "Flashcards", "Quiz"]) {
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "tabindex",
        "-1",
      );
    }
    expect(screen.getByText("其余学习资产尚未接入")).toBeInTheDocument();
    expect(screen.queryByText(/示例总结/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Transcript" }));
    expect(await screen.findByText("正文尚未生成")).toBeVisible();
  });

  it("返回路径由真实课程归属决定，空课程归属返回知识空间", async () => {
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
    expect(
      screen.queryByRole("button", { name: "删除学习记录" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "返回知识空间" }),
    ).toHaveAttribute("href", "/spaces");
  });

  it("FAILED 只显示通用失败说明且没有伪造恢复动作", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "FAILED" }),
      ),
    );
    renderAt();

    expect(await screen.findByText("学习记录处理失败")).toBeInTheDocument();
    expect(screen.getByText("当前暂无可用恢复操作。")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /重试|恢复/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/error|code|任务/)).not.toBeInTheDocument();
  });

  it("Transcript 区分确定性与可恢复失败，且终态不读取正文", async () => {
    let transcriptCalls = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          capture_type: "DOCUMENT_IMPORT",
          status: "FAILED",
        }),
      ),
      http.get(JOB_URL, () =>
        HttpResponse.json({
          id: JOB_ID,
          record_id: RECORD_ID,
          job_type: "DOCUMENT_PARSE",
          status: "FAILED",
          progress: 0,
          attempts: 1,
          max_attempts: 3,
          error_code: "FORMAT_MISMATCH",
          retryable: false,
        }),
      ),
      http.get(`${DETAIL_URL}/transcript`, () => {
        transcriptCalls += 1;
        return HttpResponse.json({ status: "NOT_READY", transcript: null });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript&jobId=${JOB_ID}`);

    expect(await screen.findByText("文件内容与扩展名不匹配。")).toBeVisible();
    expect(transcriptCalls).toBe(0);
    expect(screen.queryByRole("button", { name: /重试/ })).toBeNull();

    cleanup();
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          capture_type: "DOCUMENT_IMPORT",
          status: "FAILED",
        }),
      ),
      http.get(JOB_URL, () =>
        HttpResponse.json({
          id: JOB_ID,
          record_id: RECORD_ID,
          job_type: "DOCUMENT_PARSE",
          status: "FAILED",
          progress: 0,
          attempts: 1,
          max_attempts: 3,
          error_code: "TEMPORARY_IO",
          retryable: true,
        }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript&jobId=${JOB_ID}`);
    expect(await screen.findByText("本地文件暂时无法读取。")).toBeVisible();
    expect(screen.getByRole("button", { name: "重新处理文档" })).toBeVisible();
  });

  it("可恢复失败手动重试防重复提交，失败保留上下文且成功恢复轮询", async () => {
    let retryCalls = 0;
    let jobCalls = 0;
    let retryAccepted = false;
    let terminalJobCalls = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          capture_type: "DOCUMENT_IMPORT",
          status: retryAccepted ? "CONTENT_PROCESSING" : "FAILED",
        }),
      ),
      http.get(JOB_URL, () => {
        jobCalls += 1;
        const status = retryAccepted
          ? jobCalls >= 3
            ? "SUCCEEDED"
            : "RUNNING"
          : "FAILED";
        if (status === "SUCCEEDED") terminalJobCalls += 1;
        return HttpResponse.json({
          id: JOB_ID,
          record_id: RECORD_ID,
          job_type: "DOCUMENT_PARSE",
          status,
          progress: status === "SUCCEEDED" ? 1 : 0,
          attempts: retryAccepted ? 1 : 3,
          max_attempts: 3,
          error_code: retryAccepted ? null : "TEMPORARY_IO",
          retryable: !retryAccepted,
        });
      }),
      http.post(JOB_RETRY_URL, async ({ request }) => {
        retryCalls += 1;
        expect(await request.json()).toEqual({ record_id: RECORD_ID });
        await delay(100);
        if (retryCalls === 1) {
          return HttpResponse.json(
            { detail: "数据库暂时繁忙，请稍后重试" },
            { status: 500 },
          );
        }
        retryAccepted = true;
        return HttpResponse.json(
          {
            id: JOB_ID,
            record_id: RECORD_ID,
            job_type: "DOCUMENT_PARSE",
            status: "PENDING",
            progress: 0,
            attempts: 0,
            max_attempts: 3,
            error_code: null,
            retryable: false,
          },
          { status: 202 },
        );
      }),
      http.get(`${DETAIL_URL}/transcript`, () =>
        HttpResponse.json({
          status: "READY",
          transcript: {
            language: "und",
            content: "重试后恢复的正文",
            source_version: 1,
            edited_by_user: false,
            updated_at: "2026-08-21T12:00:00.000000Z",
          },
        }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript&jobId=${JOB_ID}`);

    const retry = await screen.findByRole("button", { name: "重新处理文档" });
    fireEvent.click(retry);
    await waitFor(() => expect(retry).toBeDisabled());
    fireEvent.click(retry);
    expect(retryCalls).toBe(1);
    expect(
      await screen.findByText("数据库暂时繁忙，请稍后重试"),
    ).toHaveAttribute("role", "alert");
    expect(screen.getByText("本地文件暂时无法读取。")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "重新处理文档" }));
    expect(await screen.findByText("正在提取文档正文")).toBeVisible();
    expect(
      await screen.findByText("重试后恢复的正文", {}, { timeout: 6_000 }),
    ).toBeVisible();
    expect(retryCalls).toBe(2);
    expect(screen.queryByRole("button", { name: "重新处理文档" })).toBeNull();

    await new Promise((resolve) => window.setTimeout(resolve, 2_200));
    expect(terminalJobCalls).toBe(1);
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

  it("删除失败保留详情并可重试，成功后刷新课程列表缓存并导航", async () => {
    let deleted = false;
    let deleteCalls = 0;
    let listCalls = 0;
    let deleteToken: string | null = null;
    server.use(
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(COURSE_RECORDS_URL, () => {
        listCalls += 1;
        return HttpResponse.json(deleted ? [] : [record]);
      }),
      http.get(DETAIL_URL, () =>
        deleted
          ? HttpResponse.json(
              { detail: "学习记录不存在或已删除" },
              { status: 404 },
            )
          : HttpResponse.json(record),
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
