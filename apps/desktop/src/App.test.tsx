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

describe("工作台骨架", () => {
  it("从今日导航到知识空间，并诚实禁用未接入入口", async () => {
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "今日" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /收件箱/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /开始录音/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("link", { name: "知识空间" }));

    expect(
      await screen.findByRole("heading", { name: "知识空间" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建知识空间" })).toBeEnabled();
  });

  it("通过真实 multipart 请求导入文档并进入记录级 Transcript", async () => {
    const course: components["schemas"]["CourseOut"] = {
      id: "11111111-1111-4111-8111-111111111111",
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
    const recordId = "22222222-2222-4222-8222-222222222222";
    const jobId = "33333333-3333-4333-8333-333333333333";
    let importCalls = 0;
    let jobCalls = 0;
    let transcriptCalls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([
          course,
          { ...course, id: "archived", name: "已归档", status: "ARCHIVED" },
        ]),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/capture-batches`, ({ request }) => {
        importCalls += 1;
        expect(request.headers.get("Content-Type")).not.toBe(
          "application/json",
        );
        return importCalls === 1
          ? HttpResponse.json(
              { detail: "UNSUPPORTED_SOURCE：不支持的来源格式" },
              { status: 400 },
            )
          : HttpResponse.json(
              { record_id: recordId, job_ids: [jobId, "job-2", "job-3"] },
              { status: 202 },
            );
      }),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
        HttpResponse.json({
          id: recordId,
          course_id: course.id,
          capture_type: "MULTI_SOURCE",
          title: "voice 等 2 个文件",
          status: "SUMMARY_PENDING",
          duration_ms: 0,
          summary_confirmed_at: null,
          created_at: "2026-08-20T08:30:00.000000Z",
          updated_at: "2026-08-20T08:30:00.000000Z",
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/jobs`, () => {
        jobCalls += 1;
        return HttpResponse.json({
          jobs: [
            {
              id: jobId,
              record_id: recordId,
              job_type: "AUDIO_TRANSCODE",
              status: "SUCCEEDED",
              progress: 1,
              attempts: 1,
              max_attempts: 3,
              error_code: null,
              retryable: false,
              waiting_reason: null,
              sequence_no: 0,
              source_name: "voice.wav",
            },
            {
              id: "job-2",
              record_id: recordId,
              job_type: "ASR",
              status: "SUCCEEDED",
              progress: 1,
              attempts: 1,
              max_attempts: 3,
              error_code: null,
              retryable: false,
              waiting_reason: null,
              sequence_no: 0,
              source_name: "voice.wav",
            },
            {
              id: "job-3",
              record_id: recordId,
              job_type: "DOCUMENT_PARSE",
              status: "SUCCEEDED",
              progress: 1,
              attempts: 1,
              max_attempts: 3,
              error_code: null,
              retryable: false,
              waiting_reason: null,
              sequence_no: 1,
              source_name: "notes.md",
            },
          ],
          progress: 1,
        });
      }),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/transcript`, () => {
        transcriptCalls += 1;
        return HttpResponse.json({
          status: "READY",
          transcript: {
            language: "und",
            content: "# 第一讲\n进程与线程",
            source_version: 1,
            edited_by_user: false,
            updated_at: "2026-08-20T08:30:01.000000Z",
          },
        });
      }),
    );

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "导入资料" }));
    expect(screen.getByRole("heading", { name: "导入资料" })).toBeVisible();
    expect(screen.queryByRole("option", { name: "已归档" })).toBeNull();
    expect(screen.getByRole("button", { name: "开始导入" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(importCalls).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "导入资料" }));
    const courseSelect = screen.getByRole("combobox", { name: "所属课程" });
    await waitFor(() => expect(courseSelect).toBeEnabled());
    fireEvent.click(courseSelect);
    const courseOption = await screen.findByRole("option", {
      name: "操作系统",
    });
    fireEvent.pointerDown(courseOption);
    fireEvent.pointerUp(courseOption);
    fireEvent.click(courseOption);
    fireEvent.change(screen.getByLabelText("选择文件"), {
      target: {
        files: [
          new File(["audio"], "voice.wav"),
          new File(["# 第一讲"], "notes.md"),
        ],
      },
    });
    const submit = screen.getByRole("button", { name: "开始导入" });
    expect(
      screen.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual(["1voice.wav", "2notes.md"]);
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    expect(
      await screen.findByText("UNSUPPORTED_SOURCE：不支持的来源格式"),
    ).toBeVisible();
    fireEvent.click(submit);
    await waitFor(() => expect(importCalls).toBe(2));
    await waitFor(
      () => expect(window.location.pathname).toBe(`/records/${recordId}`),
      { timeout: 3_000 },
    );
    await waitFor(() => expect(jobCalls).toBe(1));
    await waitFor(() => expect(transcriptCalls).toBe(1));
    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "PRE" &&
          element.textContent === "# 第一讲\n进程与线程",
      ),
    ).toBeVisible();
    expect(window.location.search).toBe("?tab=transcript");
    expect(screen.getByText("混合资料")).toBeInTheDocument();
    expect(jobCalls).toBe(1);
    expect(importCalls).toBe(2);
    await new Promise((resolve) => setTimeout(resolve, 2_200));
    expect(jobCalls).toBe(1);
    await waitFor(() =>
      expect(screen.getByText("等待生成总结")).toBeInTheDocument(),
    );
  }, 15_000);

  it("单音频可不选课程，并且 URL 不暴露任务标识", async () => {
    const recordId = "44444444-4444-4444-8444-444444444444";
    let importCalls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
      http.post(`${TEST_SIDECAR_URL}/api/capture-batches`, ({ request }) => {
        importCalls += 1;
        expect(request.headers.get("Content-Type")).not.toBe(
          "application/json",
        );
        return HttpResponse.json(
          {
            record_id: recordId,
            job_ids: [
              "55555555-5555-4555-8555-555555555555",
              "66666666-6666-4666-8666-666666666666",
            ],
          },
          { status: 202 },
        );
      }),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
        HttpResponse.json({
          id: recordId,
          course_id: null,
          capture_type: "AUDIO_IMPORT",
          title: "第一讲",
          status: "SUMMARY_PENDING",
          duration_ms: 1_000,
          summary_confirmed_at: null,
          created_at: "2026-08-22T08:30:00.000000Z",
          updated_at: "2026-08-22T08:30:00.000000Z",
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/jobs`, () =>
        HttpResponse.json({ jobs: [], progress: 1 }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}/transcript`, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
    );

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "导入资料" }));
    fireEvent.change(screen.getByLabelText("选择文件"), {
      target: { files: [new File(["RIFFaudio"], "第一讲.wav")] },
    });
    const submit = screen.getByRole("button", { name: "开始导入" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    await waitFor(() => expect(importCalls).toBe(1));
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${recordId}`),
    );
    expect(window.location.search).toBe("?tab=transcript");
  });

  it("未知地址提供返回今日的路径", async () => {
    window.history.replaceState(null, "", "/missing");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "页面不存在" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回今日" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("从受校验 URL 恢复课程搜索与筛选条件", async () => {
    let requestedUrl: URL | undefined;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        requestedUrl = new URL(request.url);
        return HttpResponse.json([]);
      }),
    );
    window.history.replaceState(
      null,
      "",
      "/spaces?q=%E6%93%8D%E4%BD%9C&education_stage=UNDERGRADUATE&course_type=MAJOR",
    );

    render(<App />);

    expect(
      await screen.findByRole("searchbox", { name: "搜索课程" }),
    ).toHaveValue("操作");
    expect(
      screen.getByRole("combobox", { name: "教育阶段筛选" }),
    ).toHaveTextContent("本科");
    expect(
      screen.getByRole("combobox", { name: "课程类型筛选" }),
    ).toHaveTextContent("专业课");
    expect(requestedUrl?.searchParams.get("q")).toBe("操作");
  });
});
