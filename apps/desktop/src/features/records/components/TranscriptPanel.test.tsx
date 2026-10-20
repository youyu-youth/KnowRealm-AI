// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
const SEGMENTS_URL = `${TRANSCRIPT_URL}/segments`;
const DOC_SEGMENTS_URL = `${DETAIL_URL}/document-segments`;
const JOB_RETRY_URL = `${TEST_SIDECAR_URL}/api/processing-jobs/${JOB_ID}/retries`;
const ASR_CONSENT_URL = `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/tencent-asr`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: "11111111-1111-4111-8111-111111111111",
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "FAILED",
  duration_ms: 0,
  summary_confirmed_at: null,
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-19T08:30:00.000000Z",
};

// 文档导入记录走 document-segments 块级数据源（票 07 集成）。
const documentRecord: RecordOut = {
  ...record,
  capture_type: "DOCUMENT_IMPORT",
  title: "docker",
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

window.Element.prototype.scrollIntoView = vi.fn();

function segment(
  overrides: Partial<components["schemas"]["TranscriptSegmentOut"]> = {},
): components["schemas"]["TranscriptSegmentOut"] {
  return {
    id: crypto.randomUUID(),
    sequence_no: 0,
    record_start_ms: null,
    record_end_ms: null,
    file_start_ms: null,
    file_end_ms: null,
    speaker: null,
    content: "",
    ...overrides,
  };
}

function documentSegment(
  overrides: Partial<components["schemas"]["DocumentSegmentOut"]> = {},
): components["schemas"]["DocumentSegmentOut"] {
  return {
    id: crypto.randomUUID(),
    sequence_no: 0,
    page_no: null,
    section_title: null,
    content: "",
    start_offset: null,
    end_offset: null,
    ...overrides,
  };
}

function readyTranscript(content: string, sourceVersion = 1) {
  return {
    status: "READY" as const,
    transcript: {
      language: "zh-CN",
      content,
      source_version: sourceVersion,
      edited_by_user: sourceVersion > 1,
      updated_at: "2026-08-21T12:00:00.000000Z",
    },
  };
}

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
  segmentId,
  enabled = true,
}: {
  detail?: RecordOut;
  highlight?: string;
  segmentId?: string;
  enabled?: boolean;
} = {}) {
  return renderWithQuery(
    <TranscriptPanel
      record={detail}
      highlight={highlight}
      segmentId={segmentId}
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
    let segmentsCalls = 0;
    let documentSegmentsCalls = 0;
    server.use(
      http.get(JOBS_URL, () => {
        jobsCalls += 1;
        return HttpResponse.json({ jobs: [], progress: 0 });
      }),
      http.get(TRANSCRIPT_URL, () => {
        transcriptCalls += 1;
        return HttpResponse.json({ status: "NOT_READY", transcript: null });
      }),
      http.get(SEGMENTS_URL, () => {
        segmentsCalls += 1;
        return HttpResponse.json([]);
      }),
      http.get(DOC_SEGMENTS_URL, () => {
        documentSegmentsCalls += 1;
        return HttpResponse.json([]);
      }),
    );
    renderTranscript({ enabled: false });
    await new Promise((resolve) => window.setTimeout(resolve, 50));
    expect(jobsCalls).toBe(0);
    expect(transcriptCalls).toBe(0);
    expect(segmentsCalls).toBe(0);

    cleanup();
    renderTranscript({ enabled: true });
    await waitFor(() => {
      expect(jobsCalls).toBe(1);
      expect(transcriptCalls).toBe(1);
    });
    // 转写未就绪时不拉分片；非文档记录永不拉文档块。
    expect(segmentsCalls).toBe(0);
    expect(documentSegmentsCalls).toBe(0);
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
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
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
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
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
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
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

  it("浏览态渲染句级时间轴，无时间戳分片无时间标记", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(
          readyTranscript("第一句在一点零五。第二句没有时间戳。"),
        ),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json([
          segment({
            sequence_no: 0,
            record_start_ms: 65_000,
            record_end_ms: 68_000,
            content: "第一句在一点零五。",
          }),
          segment({ sequence_no: 1, content: "第二句没有时间戳。" }),
          segment({
            sequence_no: 2,
            record_start_ms: 3_665_000,
            record_end_ms: 3_668_000,
            content: "第三句过了一小时。",
          }),
        ]),
      ),
    );
    renderTranscript({ detail: { ...record, status: "COMPLETED" } });

    const list = await screen.findByRole("list", { name: "来源时间轴" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(list).getByText("01:05")).toBeVisible();
    expect(within(list).getByText("1:01:05")).toBeVisible();
    // 无时间戳分片不出现时间标记，只陈列句文本。
    expect(rows[1].textContent).toBe("第二句没有时间戳。");
  });

  it("无分片 id 时引用摘录回落文本匹配：首个命中滚动高亮并显示时间戳徽章", async () => {
    const quote = "AOF 重写由阈值触发";
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(
          readyTranscript(`今天讲 Redis 持久化。${quote}。${quote} 再提一次。`),
        ),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json([
          segment({
            sequence_no: 0,
            record_start_ms: 0,
            record_end_ms: 3_000,
            content: "今天讲 Redis 持久化。",
          }),
          segment({
            sequence_no: 1,
            record_start_ms: 275_000,
            record_end_ms: 278_000,
            content: `${quote}，默认阈值是百分比。`,
          }),
          segment({
            sequence_no: 2,
            record_start_ms: 300_000,
            record_end_ms: 303_000,
            content: `${quote} 再提一次。`,
          }),
        ]),
      ),
    );
    vi.mocked(window.Element.prototype.scrollIntoView).mockClear();
    renderTranscript({
      detail: { ...record, status: "COMPLETED" },
      highlight: quote,
    });

    // 多命中取首个：唯一高亮落在第二行（04:35）并带时间戳徽章。
    const mark = await screen.findByText(quote, { selector: "mark" });
    const row = mark.closest("li");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("04:35")).toBeVisible();
    expect(document.querySelectorAll("mark")).toHaveLength(1);
    expect(window.Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("来源分片 id 优先精确定位：重复摘录落在指定分片而非首次出现", async () => {
    const quote = "AOF 重写由阈值触发";
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript(`${quote}。${quote} 再提一次。`)),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json([
          segment({
            id: "seg-275",
            sequence_no: 1,
            record_start_ms: 275_000,
            record_end_ms: 278_000,
            content: `${quote}，默认阈值是百分比。`,
          }),
          segment({
            id: "seg-300",
            sequence_no: 2,
            record_start_ms: 300_000,
            record_end_ms: 303_000,
            content: `${quote} 再提一次。`,
          }),
        ]),
      ),
    );
    vi.mocked(window.Element.prototype.scrollIntoView).mockClear();
    renderTranscript({
      detail: { ...record, status: "COMPLETED" },
      highlight: quote,
      segmentId: "seg-300",
    });

    // 文本匹配会命中的是 04:35 首次出现；分片 id 精确定位到 05:00 的第二次出现。
    const mark = await screen.findByText(quote, { selector: "mark" });
    const row = mark.closest("li");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("05:00")).toBeVisible();
    expect(within(row as HTMLElement).queryByText("04:35")).toBeNull();
    expect(document.querySelectorAll("mark")).toHaveLength(1);
    expect(window.Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("引用摘录不在任何分片时走原文已变动兜底", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript("句子一。")),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json([
          segment({ record_start_ms: 0, content: "句子一。" }),
        ]),
      ),
    );
    renderTranscript({
      detail: { ...record, status: "COMPLETED" },
      highlight: "不存在的摘录",
    });

    expect(
      await screen.findByText("原文已变动，未能定位引用内容。"),
    ).toBeVisible();
    expect(document.querySelector("mark")).toBeNull();
  });

  it("无分片记录浏览态回落纯文本", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript("粘贴的整篇文本。")),
      ),
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
    );
    renderTranscript({
      detail: { ...record, capture_type: "PASTE", status: "COMPLETED" },
    });

    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "PRE" &&
          element.textContent === "粘贴的整篇文本。",
      ),
    ).toBeVisible();
    expect(screen.queryByRole("list", { name: "来源时间轴" })).toBeNull();
  });

  it("编辑保存后重新拉取分片呈现对齐结果", async () => {
    let saved = false;
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(
          readyTranscript(
            saved ? "改写后的正文。" : "原始正文。",
            saved ? 2 : 1,
          ),
        ),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json(
          saved
            ? [
                segment({
                  sequence_no: 0,
                  record_start_ms: 3_000,
                  content: "改写后的句子。",
                }),
              ]
            : [
                segment({
                  sequence_no: 0,
                  record_start_ms: 1_000,
                  content: "原始句子。",
                }),
              ],
        ),
      ),
      http.patch(TRANSCRIPT_URL, async () => {
        saved = true;
        return HttpResponse.json({
          language: "zh-CN",
          content: "改写后的正文。",
          source_version: 2,
          edited_by_user: true,
          updated_at: "2026-08-21T12:05:00.000000Z",
        });
      }),
    );
    renderTranscript({ detail: { ...record, status: "SUMMARY_PENDING" } });

    expect(await screen.findByText("原始句子。")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "编辑正文" }));
    const editor = screen.getByRole("textbox", {
      name: "Transcript 正文编辑器",
    });
    fireEvent.change(editor, { target: { value: "改写后的正文。" } });
    fireEvent.click(screen.getByRole("button", { name: "保存正文" }));
    // 保存成功后分片被重新拉取，时间轴呈现对齐后的新句子。
    expect(await screen.findByText("改写后的句子。")).toBeVisible();
    expect(screen.queryByText("原始句子。")).toBeNull();
  });

  it("文档导入渲染块级时间轴：无标记来源时左列退为块序号", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript("# 标题\n\n第一段内容。")),
      ),
      // 新导入文档行级分片为空（依赖启动回填），时间轴走文档块。
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
      http.get(DOC_SEGMENTS_URL, () =>
        HttpResponse.json([
          documentSegment({
            sequence_no: 0,
            content: "# 标题",
            start_offset: 0,
            end_offset: 3,
          }),
          documentSegment({
            sequence_no: 1,
            content: "第一段内容。",
            start_offset: 5,
            end_offset: 10,
          }),
        ]),
      ),
    );
    renderTranscript({ detail: { ...documentRecord, status: "COMPLETED" } });

    const list = await screen.findByRole("list", { name: "来源时间轴" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    // 无时间/页码来源：左列退为块序号，时间轴结构可见。
    expect(within(list).getByText("01")).toBeVisible();
    expect(within(list).getByText("02")).toBeVisible();
  });

  it("PDF 文档块显示页码标记，引用定位命中行升级页码徽章", async () => {
    const quote = "undo 日志实现多版本读";
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript(`第一章概念。数据库靠${quote}。`)),
      ),
      http.get(SEGMENTS_URL, () => HttpResponse.json([])),
      http.get(DOC_SEGMENTS_URL, () =>
        HttpResponse.json([
          documentSegment({
            sequence_no: 0,
            page_no: 1,
            content: "第一章概念。",
            start_offset: 0,
            end_offset: 6,
          }),
          documentSegment({
            sequence_no: 1,
            page_no: 2,
            content: `数据库靠${quote}。`,
            start_offset: 6,
            end_offset: 24,
          }),
        ]),
      ),
    );
    vi.mocked(window.Element.prototype.scrollIntoView).mockClear();
    renderTranscript({
      detail: { ...documentRecord, status: "COMPLETED" },
      highlight: quote,
    });

    const mark = await screen.findByText(quote, { selector: "mark" });
    const row = mark.closest("li");
    expect(row).not.toBeNull();
    // 命中行左列页码升级为徽章；未命中页保持普通页码。
    expect(within(row as HTMLElement).getByText("第2页")).toBeVisible();
    expect(screen.getByText("第1页")).toBeVisible();
    expect(window.Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("旧文档无块分片时回落行级转写分片", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(readyTranscript("行级句。")),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json([
          segment({ record_start_ms: 1_000, content: "行级句。" }),
        ]),
      ),
      http.get(DOC_SEGMENTS_URL, () => HttpResponse.json([])),
    );
    renderTranscript({ detail: { ...documentRecord, status: "COMPLETED" } });

    const list = await screen.findByRole("list", { name: "来源时间轴" });
    expect(within(list).getByText("行级句。")).toBeVisible();
    expect(within(list).getByText("00:01")).toBeVisible();
  });

  it("文档编辑保存后块分片清零，时间轴回落行级重切结果", async () => {
    let saved = false;
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json(
          readyTranscript(
            saved ? "改后的正文。" : "原始块正文。",
            saved ? 2 : 1,
          ),
        ),
      ),
      http.get(SEGMENTS_URL, () =>
        HttpResponse.json(
          saved
            ? [segment({ sequence_no: 0, content: "重切后的行级句。" })]
            : [],
        ),
      ),
      http.get(DOC_SEGMENTS_URL, () =>
        HttpResponse.json(
          saved
            ? []
            : [
                documentSegment({
                  sequence_no: 0,
                  content: "原始块正文。",
                  start_offset: 0,
                  end_offset: 6,
                }),
              ],
        ),
      ),
      http.patch(TRANSCRIPT_URL, async () => {
        saved = true;
        return HttpResponse.json({
          language: "zh-CN",
          content: "改后的正文。",
          source_version: 2,
          edited_by_user: true,
          updated_at: "2026-08-21T12:05:00.000000Z",
        });
      }),
    );
    renderTranscript({
      detail: { ...documentRecord, status: "SUMMARY_PENDING" },
    });

    expect(await screen.findByText("原始块正文。")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "编辑正文" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Transcript 正文编辑器" }),
      { target: { value: "改后的正文。" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "保存正文" }));
    // 服务端编辑后清零文档块，前端双源失效重拉，回落行级分片。
    expect(await screen.findByText("重切后的行级句。")).toBeVisible();
    expect(screen.queryByText("原始块正文。")).toBeNull();
  });
});
