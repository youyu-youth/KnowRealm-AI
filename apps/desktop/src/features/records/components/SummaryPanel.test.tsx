// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SummaryPanel } from "@/features/records/components/SummaryPanel";
import "@/i18n";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const SUMMARY_JOBS_URL = `${DETAIL_URL}/summary-jobs`;
const SUMMARY_ADJUST_URL = `${DETAIL_URL}/summary-adjustments`;
const SUMMARY_CONFIRM_URL = `${DETAIL_URL}/summary-confirmations`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const LLM_CONSENT_URL = `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/llm`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: "11111111-1111-4111-8111-111111111111",
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "SUMMARY_PENDING",
  duration_ms: 65_000,
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

function renderSummary(detail: RecordOut = record) {
  const result = renderWithQuery(
    <SummaryPanel record={detail} onRecordAssetsChanged={vi.fn()} />,
  );
  return result.container;
}

beforeEach(() => {
  server.use(
    http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
  );
});

afterEach(cleanup);

describe("SummaryPanel", () => {
  it("未配置 Provider 时展示跳设置页的引导卡，无就地配置表单", async () => {
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "CONFIGURE_PROVIDER",
          active_job_id: null,
          blocked_reason: null,
          summary: null,
        }),
      ),
    );
    renderSummary();

    expect(
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
    expect(screen.queryByLabelText("API Key")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存 Provider" })).toBeNull();
    expect(screen.getByRole("button", { name: "前往设置" })).toBeVisible();
  });

  it("单独同意后生成，并通过 active Job 条件轮询恢复总结", async () => {
    let action: components["schemas"]["SummaryAction"] = "GRANT_CONSENT";
    let submittedAt = 0;
    server.use(
      http.get(LLM_PROVIDER_URL, () =>
        HttpResponse.json({
          provider: {
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model: "qwen-plus",
            has_api_key: true,
            api_key_hint: "••••1234",
          },
        }),
      ),
      http.get(SUMMARY_URL, () => {
        const ready = submittedAt > 0 && Date.now() - submittedAt > 600;
        return HttpResponse.json({
          action_required: action,
          active_job_id: action === "NONE" && !ready ? JOB_ID : null,
          blocked_reason: null,
          summary: ready
            ? {
                id: "55555555-5555-4555-8555-555555555555",
                record_id: RECORD_ID,
                version_no: 1,
                status: "GENERATED",
                transcript_source_version: 1,
                topic: "轮询恢复的总结",
                abstract: "通过条件轮询读取最终总结。",
                sections: [{ heading: "恢复", points: ["复用现有查询。"] }],
                prompt_version: "summary-v1",
                model: "qwen-plus",
                created_at: "2026-08-23T10:00:00Z",
              }
            : null,
        });
      }),
      http.post(LLM_CONSENT_URL, () => {
        action = "GENERATE";
        return HttpResponse.json({
          current: true,
          granted_at: "2026-08-23T10:00:00Z",
        });
      }),
      http.post(SUMMARY_JOBS_URL, () => {
        action = "NONE";
        submittedAt = Date.now();
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderSummary();

    fireEvent.click(
      await screen.findByRole("button", { name: "同意发送 Transcript" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "生成总结" }));
    expect(
      await screen.findByRole("heading", { name: "正在生成总结" }),
    ).toBeVisible();
    expect(
      await screen.findByRole(
        "heading",
        { name: "轮询恢复的总结" },
        { timeout: 3_500 },
      ),
    ).toBeVisible();
  });

  it("调整生成新版本后可确认，并刷新 Record 资产", async () => {
    const firstId = "44444444-4444-4444-8444-444444444444";
    const secondId = "66666666-6666-4666-8666-666666666666";
    let phase: "ready" | "adjusted" | "confirmed" = "ready";
    let adjustBody: { summary_id: string; feedback: string } | null = null;
    let confirmBody: { summary_id: string } | null = null;
    const summaryOf = (id: string, version: number, status: string) => ({
      id,
      record_id: RECORD_ID,
      version_no: version,
      status,
      transcript_source_version: 1,
      topic: version === 1 ? "进程调度" : "进程调度（修订版）",
      abstract: "调度器按照既定策略选择进程。",
      sections: [{ heading: "核心机制", points: ["就绪队列决定顺序。"] }],
      prompt_version: "summary-v1",
      model: "qwen-plus",
      created_at: "2026-08-23T10:00:00Z",
    });
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary:
            phase === "ready"
              ? summaryOf(firstId, 1, "GENERATED")
              : summaryOf(
                  secondId,
                  2,
                  phase === "confirmed" ? "CONFIRMED" : "GENERATED",
                ),
        }),
      ),
      http.post(SUMMARY_ADJUST_URL, async ({ request }) => {
        const body: unknown = await request.json();
        if (
          typeof body !== "object" ||
          body === null ||
          !("summary_id" in body) ||
          typeof body.summary_id !== "string" ||
          !("feedback" in body) ||
          typeof body.feedback !== "string"
        ) {
          throw new Error("总结调整请求体不符合契约");
        }
        adjustBody = {
          summary_id: body.summary_id,
          feedback: body.feedback,
        };
        phase = "adjusted";
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
      http.post(SUMMARY_CONFIRM_URL, async ({ request }) => {
        const body: unknown = await request.json();
        if (
          typeof body !== "object" ||
          body === null ||
          !("summary_id" in body) ||
          typeof body.summary_id !== "string"
        ) {
          throw new Error("总结确认请求体不符合契约");
        }
        confirmBody = { summary_id: body.summary_id };
        phase = "confirmed";
        return HttpResponse.json({
          summary: summaryOf(secondId, 2, "CONFIRMED"),
          record_status: "COMPLETED",
        });
      }),
    );
    renderSummary({ ...record, status: "SUMMARY_READY" });

    fireEvent.click(await screen.findByRole("button", { name: "调整总结" }));
    fireEvent.change(screen.getByRole("textbox", { name: "调整反馈" }), {
      target: { value: "请更简洁" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交调整" }));
    await waitFor(() =>
      expect(adjustBody).toEqual({
        summary_id: firstId,
        feedback: "请更简洁",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "进程调度（修订版）" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "确认总结" }));
    await waitFor(() => expect(confirmBody).toEqual({ summary_id: secondId }));
    expect(await screen.findByText("AI 总结 · 已确认")).toBeVisible();
  });

  it("失败可重试，课程归档阻止生成", async () => {
    let retried = false;
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: retried ? "NONE" : "RETRY",
          active_job_id: retried ? JOB_ID : null,
          blocked_reason: null,
          summary: null,
        }),
      ),
      http.post(SUMMARY_JOBS_URL, () => {
        retried = true;
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderSummary({ ...record, status: "FAILED" });
    fireEvent.click(await screen.findByRole("button", { name: "重新生成" }));
    expect(
      await screen.findByRole("heading", { name: "正在生成总结" }),
    ).toBeVisible();

    cleanup();
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "COURSE_ARCHIVED",
          summary: null,
        }),
      ),
    );
    renderSummary();
    expect(
      await screen.findByText("所属课程已归档，不能再发起新的总结。"),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "生成总结" }),
    ).not.toBeInTheDocument();

    cleanup();
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "TRANSCRIPT_NOT_READY",
          summary: null,
        }),
      ),
    );
    renderSummary({ ...record, status: "FAILED" });
    expect(await screen.findByText("Transcript 尚未准备好。")).toBeVisible();
    expect(screen.queryByRole("button", { name: /重试|恢复/ })).toBeNull();
  });

  it("调整旧版本返回 409 时展示错误并刷新当前版本", async () => {
    const firstId = "44444444-4444-4444-8444-444444444444";
    const secondId = "66666666-6666-4666-8666-666666666666";
    let rejected = false;
    const summaryOf = (id: string, topic: string) => ({
      id,
      record_id: RECORD_ID,
      version_no: id === firstId ? 1 : 2,
      status: "GENERATED",
      transcript_source_version: 1,
      topic,
      abstract: "调度器按照既定策略选择进程。",
      sections: [{ heading: "核心机制", points: ["就绪队列决定顺序。"] }],
      prompt_version: "summary-v1",
      model: "qwen-plus",
      created_at: "2026-08-23T10:00:00Z",
    });
    server.use(
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: rejected
            ? summaryOf(secondId, "进程调度（修订版）")
            : summaryOf(firstId, "进程调度"),
        }),
      ),
      http.post(SUMMARY_ADJUST_URL, () => {
        rejected = true;
        return HttpResponse.json(
          { detail: "总结已是旧版本，请刷新后重试" },
          { status: 409 },
        );
      }),
    );
    renderSummary({ ...record, status: "SUMMARY_READY" });

    fireEvent.click(await screen.findByRole("button", { name: "调整总结" }));
    fireEvent.change(screen.getByRole("textbox", { name: "调整反馈" }), {
      target: { value: "更简洁" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交调整" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "总结已是旧版本，请刷新后重试",
    );
    expect(
      await screen.findByRole("heading", { name: "进程调度（修订版）" }),
    ).toBeVisible();
  });
});
