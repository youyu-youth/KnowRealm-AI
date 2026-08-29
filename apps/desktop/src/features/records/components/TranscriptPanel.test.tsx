// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TranscriptPanel } from "@/features/records/components/TranscriptPanel";
import "@/i18n";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const JOBS_URL = `${DETAIL_URL}/jobs`;
const TRANSCRIPT_URL = `${DETAIL_URL}/transcript`;
const JOB_RETRY_URL = `${TEST_SIDECAR_URL}/api/processing-jobs/${JOB_ID}/retries`;
const ASR_CONSENT_URL = `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/tencent-asr`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: "11111111-1111-4111-8111-111111111111",
  capture_type: "DOCUMENT_IMPORT",
  title: "操作系统第一讲",
  status: "FAILED",
  duration_ms: 0,
  summary_confirmed_at: null,
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-19T08:30:00.000000Z",
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

window.Element.prototype.scrollIntoView = vi.fn();

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
    sequence_no: 0,
    source_name: null,
    ...job,
  };
  return { jobs: [completeJob], progress: completeJob.progress };
}

function renderTranscript({
  detail = record,
  highlight,
  enabled = true,
}: {
  detail?: RecordOut;
  highlight?: string;
  enabled?: boolean;
} = {}) {
  return renderWithQuery(
    <TranscriptPanel
      record={detail}
      highlight={highlight}
      enabled={enabled}
      onRecordAssetsChanged={vi.fn()}
    />,
  );
}

afterEach(cleanup);

describe("TranscriptPanel", () => {
  it("只有显式启用时才查询 Jobs 与 Transcript", async () => {
    let jobsCalls = 0;
    let transcriptCalls = 0;
    server.use(
      http.get(JOBS_URL, () => {
        jobsCalls += 1;
        return HttpResponse.json({ jobs: [], progress: 0 });
      }),
      http.get(TRANSCRIPT_URL, () => {
        transcriptCalls += 1;
        return HttpResponse.json({ status: "NOT_READY", transcript: null });
      }),
    );
    renderTranscript({ enabled: false });
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    expect(jobsCalls).toBe(0);
    expect(transcriptCalls).toBe(0);

    cleanup();
    renderTranscript({ enabled: true });
    await waitFor(() => {
      expect(jobsCalls).toBe(1);
      expect(transcriptCalls).toBe(1);
    });
  });

  it("区分确定性与可恢复失败，并防止重试重复提交", async () => {
    let retryCalls = 0;
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json(jobsResponse())),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
      http.post(JOB_RETRY_URL, async () => {
        retryCalls += 1;
        await delay(100);
        return HttpResponse.json(
          { detail: "数据库暂时繁忙，请稍后重试" },
          { status: 500 },
        );
      }),
    );
    renderTranscript();

    const retry = await screen.findByRole("button", { name: "重新处理" });
    fireEvent.click(retry);
    await waitFor(() => expect(retry).toBeDisabled());
    fireEvent.click(retry);
    expect(retryCalls).toBe(1);
    expect(
      await screen.findByText("数据库暂时繁忙，请稍后重试"),
    ).toHaveAttribute("role", "alert");
    expect(screen.getByText("本地文件暂时无法读取。")).toBeVisible();

    cleanup();
    server.use(
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          jobsResponse({ error_code: "FORMAT_MISMATCH", retryable: false }),
        ),
      ),
    );
    renderTranscript();
    expect(await screen.findByText("文件内容与扩展名不匹配。")).toBeVisible();
    expect(screen.queryByRole("button", { name: /重试/ })).toBeNull();
  });

  it("ASR 等待同意时披露外发范围并继续同一任务", async () => {
    let consentCalls = 0;
    server.use(
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          jobsResponse({
            job_type: "ASR",
            status: "PENDING",
            waiting_reason: "CONSENT_REQUIRED",
            error_code: null,
            retryable: false,
          }),
        ),
      ),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
      http.post(ASR_CONSENT_URL, () => {
        consentCalls += 1;
        return HttpResponse.json({
          granted_at: "2026-08-22T10:00:00.000000Z",
        });
      }),
    );
    renderTranscript({
      detail: { ...record, status: "CONTENT_PROCESSING" },
    });

    expect(
      await screen.findByText("首次发送前需要单独同意外部语音识别。"),
    ).toBeVisible();
    expect(
      screen.getByText(
        "原始文件保留在本机，仅转码后的音频片段会发送至腾讯云识别。",
      ),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "同意并继续识别" }));
    await waitFor(() => expect(consentCalls).toBe(1));
  });

  it("409 保留草稿，载入最新版本后可再次保存", async () => {
    let version = 1;
    let patchCalls = 0;
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({
          status: "READY",
          transcript: {
            language: "zh-CN",
            content:
              version === 1
                ? "初始正文"
                : version === 2
                  ? "服务端新版本"
                  : "合并后的正文",
            source_version: version,
            edited_by_user: version > 1,
            updated_at: "2026-08-22T10:00:00.000000Z",
          },
        }),
      ),
      http.patch(TRANSCRIPT_URL, async ({ request }) => {
        patchCalls += 1;
        const body: unknown = await request.json();
        if (
          typeof body !== "object" ||
          body === null ||
          !("content" in body) ||
          typeof body.content !== "string" ||
          !("expected_source_version" in body) ||
          typeof body.expected_source_version !== "number"
        ) {
          throw new Error("Transcript 保存请求体不符合契约");
        }
        if (patchCalls === 1) {
          version = 2;
          return HttpResponse.json(
            { detail: "Transcript 已被其他操作更新" },
            { status: 409 },
          );
        }
        version = 3;
        return HttpResponse.json({
          language: "zh-CN",
          content: body.content,
          source_version: 3,
          edited_by_user: true,
          updated_at: "2026-08-22T10:05:00.000000Z",
        });
      }),
    );
    renderTranscript({ detail: { ...record, status: "SUMMARY_PENDING" } });

    fireEvent.click(await screen.findByRole("button", { name: "编辑正文" }));
    const editor = screen.getByRole("textbox", {
      name: "Transcript 正文编辑器",
    });
    fireEvent.change(editor, { target: { value: "我的草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "保存正文" }));
    expect(await screen.findByText(/正文已在其他操作中更新/)).toBeVisible();
    expect(editor).toHaveValue("我的草稿");
    fireEvent.click(screen.getByRole("button", { name: "载入最新版本" }));
    await waitFor(() => expect(editor).toHaveValue("服务端新版本"));
    fireEvent.change(editor, { target: { value: "合并后的正文" } });
    fireEvent.click(screen.getByRole("button", { name: "保存正文" }));
    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "PRE" && element.textContent === "合并后的正文",
      ),
    ).toBeVisible();
    expect(patchCalls).toBe(2);
  });

  it("SUMMARY_PROCESSING 时禁用编辑，并高亮首个引用", async () => {
    const quote = "MVCC 依赖 undo 日志实现多版本读";
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({
          status: "READY",
          transcript: {
            language: "und",
            content: `开头。${quote}。结尾。`,
            source_version: 1,
            edited_by_user: false,
            updated_at: "2026-08-21T12:00:00.000000Z",
          },
        }),
      ),
    );
    renderTranscript({
      detail: { ...record, status: "SUMMARY_PROCESSING" },
      highlight: quote,
    });

    const mark = await screen.findByText(quote, { selector: "mark" });
    expect(mark).toBeVisible();
    expect(window.Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "编辑正文" })).toBeDisabled();
  });

  it("引用已不在转写中时显示变动提示", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({
          status: "READY",
          transcript: {
            language: "und",
            content: "转写已被整段改写。",
            source_version: 1,
            edited_by_user: false,
            updated_at: "2026-08-21T12:00:00.000000Z",
          },
        }),
      ),
    );
    renderTranscript({ highlight: "已经不存在的摘录" });

    expect(
      await screen.findByText("原文已变动，未能定位引用内容。"),
    ).toBeVisible();
    expect(document.querySelector("mark")).toBeNull();
  });

  it("终态任务只显示状态，不把重试次数当作进度", async () => {
    server.use(
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          jobsResponse({
            status: "SUCCEEDED",
            progress: 1,
            attempts: 1,
            error_code: null,
            retryable: false,
          }),
        ),
      ),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
    );
    renderTranscript({ detail: { ...record, status: "SUMMARY_PENDING" } });

    expect(await screen.findByText("已完成")).toBeVisible();
    expect(screen.queryByText(/第 1 次尝试/)).toBeNull();
  });
});
