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

  it("通过真实 multipart 请求导入文档并进入可轮询的 Transcript", async () => {
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
      http.post(`${TEST_SIDECAR_URL}/api/document-imports`, ({ request }) => {
        importCalls += 1;
        expect(request.headers.get("Content-Type")).not.toBe(
          "application/json",
        );
        return HttpResponse.json(
          { record_id: recordId, job_id: jobId },
          { status: 202 },
        );
      }),
      http.get(`${TEST_SIDECAR_URL}/api/records/${recordId}`, () =>
        HttpResponse.json({
          id: recordId,
          course_id: course.id,
          capture_type: "DOCUMENT_IMPORT",
          title: "lecture",
          status: jobCalls === 0 ? "CONTENT_PROCESSING" : "SUMMARY_PENDING",
          duration_ms: 0,
          summary_confirmed_at: null,
          created_at: "2026-08-20T08:30:00.000000Z",
          updated_at: "2026-08-20T08:30:00.000000Z",
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/processing-jobs/${jobId}`, () => {
        jobCalls += 1;
        return HttpResponse.json({
          id: jobId,
          record_id: recordId,
          job_type: "DOCUMENT_PARSE",
          status: jobCalls === 1 ? "PENDING" : "SUCCEEDED",
          progress: jobCalls === 1 ? 0 : 1,
          attempts: jobCalls === 1 ? 0 : 1,
          max_attempts: 3,
          error_code: null,
          retryable: false,
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
    expect(screen.getByRole("heading", { name: "导入单个文档" })).toBeVisible();
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
    fireEvent.change(screen.getByLabelText("选择文档"), {
      target: { files: [new File(["# 第一讲"], "lecture.md")] },
    });
    const submit = screen.getByRole("button", { name: "开始导入" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);

    await waitFor(() => expect(importCalls).toBe(1));
    await waitFor(
      () => expect(window.location.pathname).toBe(`/records/${recordId}`),
      { timeout: 3_000 },
    );
    await waitFor(() => expect(jobCalls).toBe(2), { timeout: 5_000 });
    await waitFor(() => expect(transcriptCalls).toBe(1));
    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "PRE" &&
          element.textContent === "# 第一讲\n进程与线程",
      ),
    ).toBeVisible();
    expect(window.location.search).toBe(`?tab=transcript&jobId=${jobId}`);
    expect(jobCalls).toBe(2);
    expect(importCalls).toBe(1);
    await waitFor(() =>
      expect(screen.getByText("等待生成总结")).toBeInTheDocument(),
    );
  }, 15_000);

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
