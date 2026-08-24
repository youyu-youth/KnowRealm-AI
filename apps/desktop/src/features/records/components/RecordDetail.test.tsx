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
const JOB_RETRY_URL = `${TEST_SIDECAR_URL}/api/processing-jobs/${JOB_ID}/retries`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const SUMMARY_JOBS_URL = `${DETAIL_URL}/summary-jobs`;
const SUMMARY_ADJUST_URL = `${DETAIL_URL}/summary-adjustments`;
const SUMMARY_CONFIRM_URL = `${DETAIL_URL}/summary-confirmations`;
const KNOWLEDGE_POINTS_URL = `${DETAIL_URL}/knowledge-points`;
const KNOWLEDGE_POINT_JOBS_URL = `${DETAIL_URL}/knowledge-point-jobs`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const LLM_TEST_URL = `${LLM_PROVIDER_URL}/tests`;
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

function draftKnowledgePoint(
  overrides: Partial<components["schemas"]["KnowledgePointOut"]> = {},
): components["schemas"]["KnowledgePointOut"] {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    record_id: RECORD_ID,
    batch_id: JOB_ID,
    name: "进程调度",
    detail: "调度器从就绪队列中选择下一个运行的进程。",
    tags: ["操作系统"],
    importance: 5,
    generated_from_summary_id: "55555555-5555-4555-8555-555555555555",
    generation_status: "DRAFT",
    created_at: "2026-08-24T12:00:00.000000Z",
    updated_at: "2026-08-24T12:00:00.000000Z",
    ...overrides,
  };
}

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

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
      screen.getByText("习题、复习、Todo 与 Ask AI 尚未接入"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/示例总结/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Transcript" }));
    expect(await screen.findByText("正文尚未生成")).toBeVisible();
  });

  it("配置 Provider 时密钥不回显，保存后可测试连接再继续", async () => {
    let savedProvider: components["schemas"]["LlmProviderOut"] | null = null;
    let savedBody: components["schemas"]["LlmProviderUpdate"] | null = null;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: savedProvider
            ? "GRANT_CONSENT"
            : "CONFIGURE_PROVIDER",
          active_job_id: null,
          blocked_reason: null,
          summary: null,
        }),
      ),
      http.get(LLM_PROVIDER_URL, () =>
        HttpResponse.json({ provider: savedProvider }),
      ),
      http.put(LLM_PROVIDER_URL, async ({ request }) => {
        savedBody =
          (await request.json()) as components["schemas"]["LlmProviderUpdate"];
        savedProvider = {
          base_url: savedBody.base_url,
          model: savedBody.model,
          has_api_key: true,
          api_key_hint: "sk-…1234",
        };
        return HttpResponse.json({ provider: savedProvider });
      }),
      http.post(LLM_TEST_URL, () =>
        HttpResponse.json({ ok: true, model: "qwen-plus" }),
      ),
    );
    renderAt();

    expect(
      await screen.findByRole("heading", { name: "配置 AI Provider" }),
    ).toBeInTheDocument();
    expect(screen.queryByDisplayValue(/sk-/)).not.toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("API Key"), {
      target: { value: "sk-secret-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Provider" }));
    await waitFor(() => expect(savedBody?.api_key).toBe("sk-secret-1234"));
    expect(screen.getByLabelText("API Key")).toHaveValue("");
    fireEvent.click(await screen.findByRole("button", { name: "测试连接" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "连接测试成功（qwen-plus）",
    );
    fireEvent.change(screen.getByLabelText("模型"), {
      target: { value: "qwen-max" },
    });
    await waitFor(() => {
      expect(
        screen.queryByText("连接测试成功（qwen-plus）"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "继续" }),
      ).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Provider" }));
    await waitFor(() => expect(savedBody?.model).toBe("qwen-max"));
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(
      await screen.findByRole("heading", { name: "同意外部 AI 处理" }),
    ).toBeInTheDocument();
  });

  it("知识点页签按 PRD 命名落地，未确认总结时引导返回 Summary", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: [],
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "SUMMARY_NOT_CONFIRMED",
          input_mode: null,
        }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "请先确认总结" }),
    ).toBeVisible();
    expect(screen.getByRole("tab", { name: "知识点" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    for (const label of ["习题", "复习", "Todo", "Ask AI"]) {
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
    }
    fireEvent.click(screen.getByRole("button", { name: "前往 Summary" }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
  });

  it("知识点缺少 Provider 时打开可操作的配置态", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: [],
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "PROVIDER_NOT_CONFIGURED",
          input_mode: null,
        }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: null,
        }),
      ),
      http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(
      await screen.findByRole("button", { name: "前往 Summary" }),
    );
    expect(
      await screen.findByRole("heading", { name: "配置 AI Provider" }),
    ).toBeVisible();
  });

  it("知识点同意失效时可原地授权并恢复生成入口", async () => {
    let consentGranted = false;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: [],
          action_required: consentGranted ? "GENERATE" : "NONE",
          active_job_id: null,
          blocked_reason: consentGranted ? null : "CONSENT_REQUIRED",
          input_mode: null,
        }),
      ),
      http.post(LLM_CONSENT_URL, () => {
        consentGranted = true;
        return HttpResponse.json({
          current: true,
          granted_at: "2026-08-24T10:00:00Z",
        });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByText(
        "生成时将向当前 Provider 发送课程上下文、已确认总结与 Transcript；超长 Transcript 仅发送总结。",
      ),
    ).toBeVisible();
    fireEvent.click(
      await screen.findByRole("button", { name: "同意并继续生成" }),
    );
    expect(
      await screen.findByRole("button", { name: "生成候选知识点" }),
    ).toBeVisible();
  });

  it("生成后轮询展示持久化候选，并明示超长输入基于总结提取", async () => {
    let submittedAt = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () => {
        const done = submittedAt > 0 && Date.now() - submittedAt > 700;
        return HttpResponse.json({
          items: done
            ? [
                {
                  id: "44444444-4444-4444-8444-444444444444",
                  record_id: RECORD_ID,
                  batch_id: JOB_ID,
                  name: "进程调度",
                  detail: "调度器从就绪队列中选择下一个运行的进程。",
                  tags: ["操作系统", "调度"],
                  importance: 5,
                  generated_from_summary_id:
                    "55555555-5555-4555-8555-555555555555",
                  generation_status: "DRAFT",
                  created_at: "2026-08-24T12:00:00.000000Z",
                  updated_at: "2026-08-24T12:00:00.000000Z",
                },
              ]
            : [],
          action_required: done ? "CONFIRM" : submittedAt ? "NONE" : "GENERATE",
          active_job_id: !done && submittedAt ? JOB_ID : null,
          blocked_reason: null,
          input_mode: "SUMMARY_ONLY",
        });
      }),
      http.post(KNOWLEDGE_POINT_JOBS_URL, () => {
        submittedAt = Date.now();
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(
      await screen.findByRole("button", { name: "生成候选知识点" }),
    );
    expect(await screen.findByText("正在生成知识点")).toBeVisible();
    expect(
      await screen.findByRole(
        "heading",
        { name: "进程调度" },
        { timeout: 4_000 },
      ),
    ).toBeVisible();
    expect(screen.getByText("基于总结提取")).toBeVisible();
    expect(
      screen.getByRole("group", { name: "进程调度 · 重要度 5 / 5" }),
    ).toBeVisible();
    expect(screen.getByText("#操作系统")).toBeVisible();
  });

  it("知识点生成失败可手动重试", async () => {
    let retried = false;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: retried
            ? [
                {
                  id: "44444444-4444-4444-8444-444444444444",
                  record_id: RECORD_ID,
                  batch_id: JOB_ID,
                  name: "重试后的候选",
                  detail: "候选已由复用的失败任务生成。",
                  tags: [],
                  importance: 3,
                  generated_from_summary_id:
                    "55555555-5555-4555-8555-555555555555",
                  generation_status: "DRAFT",
                  created_at: "2026-08-24T12:00:00.000000Z",
                  updated_at: "2026-08-24T12:00:00.000000Z",
                },
              ]
            : [],
          action_required: retried ? "CONFIRM" : "RETRY",
          active_job_id: null,
          blocked_reason: null,
          input_mode: "FULL_TRANSCRIPT",
        }),
      ),
      http.post(KNOWLEDGE_POINT_JOBS_URL, () => {
        retried = true;
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(await screen.findByRole("button", { name: "重试生成" }));
    expect(
      await screen.findByRole("heading", { name: "重试后的候选" }),
    ).toBeVisible();
  });

  it("候选审阅支持星级即时调整、编辑与删除", async () => {
    const firstId = "44444444-4444-4444-8444-444444444444";
    const secondId = "66666666-6666-4666-8666-666666666666";
    const patchBodies: components["schemas"]["KnowledgePointWriteRequest"][] =
      [];
    let items: components["schemas"]["KnowledgePointOut"][] = [
      draftKnowledgePoint(),
      draftKnowledgePoint({
        id: secondId,
        name: "时间片",
        importance: 4,
        tags: [],
      }),
    ];
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items,
          action_required: items.length ? "CONFIRM" : "GENERATE",
          active_job_id: null,
          blocked_reason: null,
          input_mode: "FULL_TRANSCRIPT",
        }),
      ),
      http.patch(`${KNOWLEDGE_POINTS_URL}/${firstId}`, async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["KnowledgePointWriteRequest"];
        patchBodies.push(body);
        items = items.map((item) =>
          item.id === firstId
            ? { ...item, ...body, updated_at: "2026-08-24T12:10:00.000000Z" }
            : item,
        );
        return HttpResponse.json(items.find((item) => item.id === firstId));
      }),
      http.delete(`${KNOWLEDGE_POINTS_URL}/${secondId}`, () => {
        items = items.filter((item) => item.id !== secondId);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "把 进程调度 设为重要度 2" }),
    );
    await waitFor(() => expect(patchBodies[0]?.importance).toBe(2));
    expect(
      screen.getByRole("group", { name: "进程调度 · 重要度 2 / 5" }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "编辑 进程调度" }));
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "调度器" },
    });
    fireEvent.change(screen.getByLabelText("详情"), {
      target: { value: "调度器决定处理器时间的分配对象。" },
    });
    fireEvent.change(screen.getByLabelText("标签"), {
      target: { value: "操作系统，调度" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    expect(
      await screen.findByRole("heading", { name: "调度器" }),
    ).toBeVisible();
    expect(patchBodies[1]).toMatchObject({
      name: "调度器",
      detail: "调度器决定处理器时间的分配对象。",
      tags: ["操作系统", "调度"],
      importance: 2,
    });

    fireEvent.click(screen.getByRole("button", { name: "删除 时间片" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "时间片" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "确认保存" })).toBeVisible();
  });

  it("手工补充即时保存为独立知识点", async () => {
    let items: components["schemas"]["KnowledgePointOut"][] = [
      draftKnowledgePoint(),
    ];
    let createdBody:
      components["schemas"]["KnowledgePointWriteRequest"] | null = null;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items,
          action_required: items.length ? "CONFIRM" : "GENERATE",
          active_job_id: null,
          blocked_reason: null,
          input_mode: "FULL_TRANSCRIPT",
        }),
      ),
      http.post(KNOWLEDGE_POINTS_URL, async ({ request }) => {
        createdBody =
          (await request.json()) as components["schemas"]["KnowledgePointWriteRequest"];
        const created = draftKnowledgePoint({
          id: "77777777-7777-4777-8777-777777777777",
          name: createdBody.name,
          detail: createdBody.detail,
          tags: createdBody.tags,
          importance: createdBody.importance,
          batch_id: null,
          generated_from_summary_id: null,
          generation_status: "ACTIVE",
        });
        items = [...items, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(await screen.findByRole("button", { name: "添加知识点" }));
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "手工补充：就绪队列" },
    });
    fireEvent.change(screen.getByLabelText("详情"), {
      target: { value: "就绪队列保存可运行进程。" },
    });
    fireEvent.change(screen.getByLabelText("标签"), {
      target: { value: "手工，队列" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(
      await screen.findByRole("heading", { name: "手工补充：就绪队列" }),
    ).toBeVisible();
    expect(createdBody).toMatchObject({
      name: "手工补充：就绪队列",
      detail: "就绪队列保存可运行进程。",
      tags: ["手工", "队列"],
      importance: 3,
    });
    expect(screen.getByText("已保存到本地 · 待确认")).toBeVisible();
  });

  it("确认批次后候选转为正式知识点且列表保持稳定", async () => {
    let confirmed = false;
    const draftItems = [
      draftKnowledgePoint(),
      draftKnowledgePoint({
        id: "66666666-6666-4666-8666-666666666666",
        name: "时间片",
        importance: 4,
        tags: [],
      }),
    ];
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: confirmed
            ? draftItems.map((item) => ({
                ...item,
                generation_status: "ACTIVE" as const,
              }))
            : draftItems,
          action_required: confirmed ? "NONE" : "CONFIRM",
          active_job_id: null,
          blocked_reason: null,
          input_mode: null,
        }),
      ),
      http.post(
        `${DETAIL_URL}/knowledge-point-batches/${JOB_ID}/confirmations`,
        () => {
          confirmed = true;
          return HttpResponse.json({
            items: draftItems.map((item) => ({
              ...item,
              generation_status: "ACTIVE" as const,
            })),
            action_required: "NONE",
            active_job_id: null,
            blocked_reason: null,
            input_mode: null,
          });
        },
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "候选知识点" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "确认保存" }));
    expect(
      await screen.findByRole("heading", { name: "知识点" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "确认保存" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "丢弃整批" }),
    ).not.toBeInTheDocument();
    expect(
      screen
        .getAllByRole("heading", { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(["进程调度", "时间片"]);
    expect(screen.getByText("已保存到本地 · 按重要度排序")).toBeVisible();
  });

  it("确认被换代阻止时给出丢弃重生成引导", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: [draftKnowledgePoint()],
          action_required: "CONFIRM",
          active_job_id: null,
          blocked_reason: null,
          input_mode: "FULL_TRANSCRIPT",
        }),
      ),
      http.post(
        `${DETAIL_URL}/knowledge-point-batches/${JOB_ID}/confirmations`,
        () =>
          HttpResponse.json(
            { detail: "总结已换代或课程已归档，请丢弃当前候选后重新生成" },
            { status: 409 },
          ),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(await screen.findByRole("button", { name: "确认保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "总结已换代或课程已归档，请丢弃当前候选后重新生成",
    );
    expect(screen.getByRole("heading", { name: "候选知识点" })).toBeVisible();
    expect(screen.getByRole("button", { name: "丢弃整批" })).toBeVisible();
  });

  it("丢弃整批候选回到可重新生成的初始态", async () => {
    let discarded = false;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json(
          discarded
            ? {
                items: [],
                action_required: "GENERATE",
                active_job_id: null,
                blocked_reason: null,
                input_mode: null,
              }
            : {
                items: [draftKnowledgePoint()],
                action_required: "CONFIRM",
                active_job_id: null,
                blocked_reason: null,
                input_mode: "FULL_TRANSCRIPT",
              },
        ),
      ),
      http.post(
        `${DETAIL_URL}/knowledge-point-batches/${JOB_ID}/discards`,
        () => {
          discarded = true;
          return HttpResponse.json({
            items: [],
            action_required: "GENERATE",
            active_job_id: null,
            blocked_reason: null,
            input_mode: null,
          });
        },
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "候选知识点" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "丢弃整批" }));
    expect(
      await screen.findByRole("button", { name: "生成候选知识点" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "进程调度" }),
    ).not.toBeInTheDocument();
  });

  it("确认后仍可编辑、删除与手工补充", async () => {
    const itemId = "44444444-4444-4444-8444-444444444444";
    let items: components["schemas"]["KnowledgePointOut"][] = [
      draftKnowledgePoint({ generation_status: "ACTIVE" }),
    ];
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items,
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          input_mode: null,
        }),
      ),
      http.patch(`${KNOWLEDGE_POINTS_URL}/${itemId}`, async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["KnowledgePointWriteRequest"];
        items = items.map((item) =>
          item.id === itemId ? { ...item, ...body } : item,
        );
        return HttpResponse.json(items.find((item) => item.id === itemId));
      }),
      http.post(KNOWLEDGE_POINTS_URL, async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["KnowledgePointWriteRequest"];
        const created = draftKnowledgePoint({
          id: "77777777-7777-4777-8777-777777777777",
          name: body.name,
          detail: body.detail,
          tags: body.tags,
          importance: body.importance,
          batch_id: null,
          generated_from_summary_id: null,
          generation_status: "ACTIVE",
        });
        items = [...items, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "知识点" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "编辑 进程调度" }));
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "确认后的编辑" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    expect(
      await screen.findByRole("heading", { name: "确认后的编辑" }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "添加知识点" }));
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "确认后的补充" },
    });
    fireEvent.change(screen.getByLabelText("详情"), {
      target: { value: "继续补充的内容。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(
      await screen.findByRole("heading", { name: "确认后的补充" }),
    ).toBeVisible();
  });

  it("单独同意后可明确生成，错过 Worker 事件仍通过条件轮询恢复", async () => {
    let action: components["schemas"]["SummaryAction"] = "GRANT_CONSENT";
    let consentCalls = 0;
    let submitCalls = 0;
    let submittedAt = 0;
    let releaseProvider!: () => void;
    const providerReady = new Promise<void>((resolve) => {
      releaseProvider = resolve;
    });
    let providerRequests = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(LLM_PROVIDER_URL, async () => {
        providerRequests += 1;
        await providerReady;
        return HttpResponse.json({
          provider: {
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model: "qwen-plus",
            has_api_key: true,
            api_key_hint: "••••1234",
          },
        });
      }),
      http.put(LLM_PROVIDER_URL, async ({ request }) => {
        const body =
          (await request.json()) as components["schemas"]["LlmProviderUpdate"];
        return HttpResponse.json({
          provider: {
            base_url: body.base_url,
            model: body.model,
            has_api_key: true,
            api_key_hint: "••••1234",
          },
        });
      }),
      http.get(SUMMARY_URL, () => {
        const ready = submittedAt > 0 && Date.now() - submittedAt > 1_000;
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
                abstract:
                  "页面在错过 Worker 状态切换事件后，通过 active Job 条件轮询读取到最终总结。",
                sections: [
                  { heading: "恢复", points: ["没有创建第二条事件流。"] },
                ],
                prompt_version: "summary-v1",
                model: "qwen-plus",
                created_at: "2026-08-23T10:00:00Z",
              }
            : null,
        });
      }),
      http.post(LLM_CONSENT_URL, () => {
        consentCalls += 1;
        action = "GENERATE";
        return HttpResponse.json({
          current: true,
          granted_at: "2026-08-23T10:00:00Z",
        });
      }),
      http.post(SUMMARY_JOBS_URL, () => {
        submitCalls += 1;
        action = "NONE";
        submittedAt = Date.now();
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderAt();

    await waitFor(() => expect(providerRequests).toBe(1));
    expect(
      screen.queryByRole("button", { name: "同意发送 Transcript" }),
    ).not.toBeInTheDocument();
    releaseProvider();
    expect(
      await screen.findByText(/当前 Provider：qwen-plus/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "更改 Provider" }));
    expect(
      await screen.findByLabelText("清除已保存的 API Key"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("模型"), {
      target: { value: "qwen-max" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Provider" }));
    fireEvent.click(await screen.findByRole("button", { name: "继续" }));
    expect(
      await screen.findByText(/当前 Provider：qwen-max/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/当前 Provider：qwen-plus/),
    ).not.toBeInTheDocument();
    expect(providerRequests).toBe(1);
    fireEvent.click(
      await screen.findByRole("button", { name: "同意发送 Transcript" }),
    );
    expect(
      await screen.findByRole("button", { name: "生成总结" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成总结" }));
    expect(
      await screen.findByRole("heading", { name: "正在生成总结" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole(
        "heading",
        { name: "轮询恢复的总结" },
        { timeout: 3_500 },
      ),
    ).toBeInTheDocument();
    expect(consentCalls).toBe(1);
    expect(submitCalls).toBe(1);
  });

  it("展示真实结构化总结并明确标为待确认", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "SUMMARY_READY" }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: {
            id: "44444444-4444-4444-8444-444444444444",
            record_id: RECORD_ID,
            version_no: 1,
            status: "GENERATED",
            transcript_source_version: 1,
            topic: "虚拟内存",
            abstract:
              "虚拟内存通过地址空间抽象隔离进程，并借助分页机制按需映射物理内存。",
            sections: [
              {
                heading: "核心机制",
                points: ["页表完成虚拟地址到物理地址的转换。"],
              },
            ],
            prompt_version: "summary-v1",
            model: "qwen-plus",
            user_feedback: null,
            created_at: "2026-08-23T10:00:00Z",
          },
        }),
      ),
    );
    renderAt();

    expect(
      await screen.findByRole("heading", { name: "虚拟内存" }),
    ).toBeInTheDocument();
    expect(screen.getByText("AI 生成 · 待确认")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "核心机制" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "确认总结" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "调整总结" }),
    ).toBeInTheDocument();
  });

  it("调整生成新版本后确认完成，未实现入口保持禁用", async () => {
    const firstId = "44444444-4444-4444-8444-444444444444";
    const secondId = "66666666-6666-4666-8666-666666666666";
    let phase: "ready" | "processing" | "adjusted" | "confirmed" = "ready";
    let adjustedAt = 0;
    let adjustBody: { summary_id: string; feedback: string } | null = null;
    let confirmBody: { summary_id: string } | null = null;
    const summaryOf = (id: string, version: number, status: string) => ({
      id,
      record_id: RECORD_ID,
      version_no: version,
      status,
      transcript_source_version: 1,
      topic: version === 1 ? "进程调度" : "进程调度（修订版）",
      abstract:
        version === 1
          ? "调度器按照既定策略选择下一个获得处理器的进程。"
          : "根据反馈修订后的摘要内容。",
      sections: [{ heading: "核心机制", points: ["就绪队列决定候选顺序。"] }],
      prompt_version: version === 1 ? "summary-v1" : "summary-adjust-v1",
      model: "qwen-plus",
      user_feedback: version === 1 ? null : "请更简洁，侧重调度策略",
      created_at: "2026-08-23T10:00:00Z",
    });
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          status: phase === "confirmed" ? "COMPLETED" : "SUMMARY_READY",
        }),
      ),
      http.get(SUMMARY_URL, () => {
        if (phase === "processing" && Date.now() - adjustedAt > 300) {
          phase = "adjusted";
        }
        if (phase === "ready")
          return HttpResponse.json({
            action_required: "NONE",
            active_job_id: null,
            blocked_reason: null,
            summary: summaryOf(firstId, 1, "GENERATED"),
          });
        if (phase === "processing")
          return HttpResponse.json({
            action_required: "NONE",
            active_job_id: JOB_ID,
            blocked_reason: null,
            summary: null,
          });
        return HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: summaryOf(
            secondId,
            2,
            phase === "confirmed" ? "CONFIRMED" : "GENERATED",
          ),
        });
      }),
      http.post(SUMMARY_ADJUST_URL, async ({ request }) => {
        adjustBody = (await request.json()) as {
          summary_id: string;
          feedback: string;
        };
        phase = "processing";
        adjustedAt = Date.now();
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
      http.post(SUMMARY_CONFIRM_URL, async ({ request }) => {
        confirmBody = (await request.json()) as { summary_id: string };
        phase = "confirmed";
        return HttpResponse.json({
          summary: summaryOf(secondId, 2, "CONFIRMED"),
          record_status: "COMPLETED",
        });
      }),
    );
    renderAt();

    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "调整总结" }));
    const feedbackInput = screen.getByRole("textbox", {
      name: "调整反馈",
    });
    expect(screen.getByRole("button", { name: "提交调整" })).toBeDisabled();
    fireEvent.change(feedbackInput, {
      target: { value: "请更简洁，侧重调度策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交调整" }));
    await waitFor(() =>
      expect(adjustBody).toEqual({
        summary_id: firstId,
        feedback: "请更简洁，侧重调度策略",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "正在生成总结" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole(
        "heading",
        { name: "进程调度（修订版）" },
        { timeout: 3_500 },
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认总结" }));
    await waitFor(() => expect(confirmBody).toEqual({ summary_id: secondId }));
    expect(await screen.findByText("AI 总结 · 已确认")).toBeInTheDocument();
    expect(
      screen.getByText("总结已确认；习题、复习、Todo 与 Ask AI 尚未接入"),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "知识点" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    for (const label of ["习题", "复习", "Todo", "Ask AI"]) {
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
    }
    expect(
      screen.queryByRole("button", { name: "确认总结" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "调整总结" }),
    ).not.toBeInTheDocument();
  }, 10_000);

  it("调整返回 409 时提示旧版本并刷新到当前版本", async () => {
    const firstId = "44444444-4444-4444-8444-444444444444";
    const secondId = "66666666-6666-4666-8666-666666666666";
    let rejected = false;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "SUMMARY_READY" }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: rejected
            ? {
                id: secondId,
                record_id: RECORD_ID,
                version_no: 2,
                status: "GENERATED",
                transcript_source_version: 1,
                topic: "进程调度（修订版）",
                abstract: "另一端已生成的新版本。",
                sections: [
                  { heading: "核心机制", points: ["就绪队列决定候选顺序。"] },
                ],
                prompt_version: "summary-adjust-v1",
                model: "qwen-plus",
                user_feedback: "别处的反馈",
                created_at: "2026-08-23T10:05:00Z",
              }
            : {
                id: firstId,
                record_id: RECORD_ID,
                version_no: 1,
                status: "GENERATED",
                transcript_source_version: 1,
                topic: "进程调度",
                abstract: "调度器按照既定策略选择下一个获得处理器的进程。",
                sections: [
                  { heading: "核心机制", points: ["就绪队列决定候选顺序。"] },
                ],
                prompt_version: "summary-v1",
                model: "qwen-plus",
                user_feedback: null,
                created_at: "2026-08-23T10:00:00Z",
              },
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
    renderAt();

    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "调整总结" }));
    fireEvent.change(screen.getByRole("textbox", { name: "调整反馈" }), {
      target: { value: "更简洁" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交调整" }));
    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent(
      "总结已是旧版本，请刷新后重试",
    );
    expect(
      await screen.findByRole("heading", { name: "进程调度（修订版）" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "确认总结" }),
    ).toBeInTheDocument();
  });

  it("总结失败可明确重试，课程归档则不提供生成动作", async () => {
    let retried = false;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "FAILED" }),
      ),
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
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "重新生成" }));
    expect(
      await screen.findByRole("heading", { name: "正在生成总结" }),
    ).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "COURSE_ARCHIVED",
          summary: null,
        }),
      ),
    );
    renderAt();
    expect(
      await screen.findByText("所属课程已归档，不能再发起新的总结。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "生成总结" }),
    ).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "删除学习记录" })).toBeVisible();
    expect(
      await screen.findByRole("link", { name: "返回知识空间" }),
    ).toHaveAttribute("href", "/spaces");
  });

  it("正文未就绪的 FAILED 记录不伪造恢复动作", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "FAILED" }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "TRANSCRIPT_NOT_READY",
          summary: null,
        }),
      ),
    );
    renderAt();

    expect(
      await screen.findByText("Transcript 尚未准备好。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /重试|恢复/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/error|code|任务/)).not.toBeInTheDocument();
  });

  it("Transcript 区分确定性与可恢复失败", async () => {
    let transcriptCalls = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          capture_type: "DOCUMENT_IMPORT",
          status: "FAILED",
        }),
      ),
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          jobsResponse({ error_code: "FORMAT_MISMATCH", retryable: false }),
        ),
      ),
      http.get(`${DETAIL_URL}/transcript`, () => {
        transcriptCalls += 1;
        return HttpResponse.json({ status: "NOT_READY", transcript: null });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript`);

    expect(await screen.findByText("文件内容与扩展名不匹配。")).toBeVisible();
    expect(transcriptCalls).toBe(1);
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
      http.get(JOBS_URL, () => HttpResponse.json(jobsResponse())),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript`);
    expect(await screen.findByText("本地文件暂时无法读取。")).toBeVisible();
    expect(screen.getByText("失败 · 第 1 次尝试（最多 3 次）")).toBeVisible();
    expect(screen.getByRole("button", { name: "重新处理" })).toBeVisible();
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
          status:
            retryAccepted && jobCalls >= 3
              ? "SUMMARY_PENDING"
              : retryAccepted
                ? "CONTENT_PROCESSING"
                : "FAILED",
        }),
      ),
      http.get(JOBS_URL, () => {
        jobCalls += 1;
        const status = retryAccepted
          ? jobCalls >= 3
            ? "SUCCEEDED"
            : "RUNNING"
          : "FAILED";
        if (status === "SUCCEEDED") terminalJobCalls += 1;
        return HttpResponse.json(
          jobsResponse({
            status,
            progress: status === "SUCCEEDED" ? 1 : 0,
            attempts: retryAccepted ? 1 : 3,
            error_code: retryAccepted ? null : "TEMPORARY_IO",
            retryable: !retryAccepted,
          }),
        );
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
            waiting_reason: null,
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
    renderAt(`${ROUTE_PATH}?tab=transcript`);

    const retry = await screen.findByRole("button", { name: "重新处理" });
    fireEvent.click(retry);
    await waitFor(() => expect(retry).toBeDisabled());
    fireEvent.click(retry);
    expect(retryCalls).toBe(1);
    expect(
      await screen.findByText("数据库暂时繁忙，请稍后重试"),
    ).toHaveAttribute("role", "alert");
    expect(screen.getByText("本地文件暂时无法读取。")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "重新处理" }));
    expect(
      await screen.findByText("重试后恢复的正文", {}, { timeout: 6_000 }),
    ).toBeVisible();
    expect(retryCalls).toBe(2);
    expect(screen.queryByRole("button", { name: "重新处理" })).toBeNull();

    await screen.findByText("等待生成总结", {}, { timeout: 6_000 });
    const callsAtTerminal = terminalJobCalls;
    await new Promise((resolve) => window.setTimeout(resolve, 2_200));
    expect(terminalJobCalls).toBe(callsAtTerminal);
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

  it("独立同意后继续同一 ASR 任务", async () => {
    let consentCalls = 0;
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "CONTENT_PROCESSING" }),
      ),
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
      http.get(`${DETAIL_URL}/transcript`, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
      http.get(`${DETAIL_URL}/events`, () =>
        HttpResponse.json({ detail: "stream unavailable" }, { status: 503 }),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/tencent-asr`,
        ({ request }) => {
          consentCalls += 1;
          expect(request.headers.get("X-KnowRealm-Token")).toBe(
            TEST_LAUNCH_TOKEN,
          );
          return HttpResponse.json({
            granted_at: "2026-08-22T10:00:00.000000Z",
          });
        },
      ),
    );

    renderAt(`${ROUTE_PATH}?tab=transcript`);

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

  it("Transcript 409 保留草稿，载入新版本后可成功保存", async () => {
    let version = 1;
    let patchCalls = 0;
    let transcriptGets = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(`${DETAIL_URL}/transcript`, () => {
        transcriptGets += 1;
        return HttpResponse.json({
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
        });
      }),
      http.patch(`${DETAIL_URL}/transcript`, async ({ request }) => {
        patchCalls += 1;
        const payload = (await request.json()) as {
          content: string;
          expected_source_version: number;
        };
        if (patchCalls === 1) {
          expect(payload).toEqual({
            content: "我的草稿",
            expected_source_version: 1,
          });
          version = 2;
          return HttpResponse.json(
            { detail: "Transcript 已被其他操作更新" },
            { status: 409 },
          );
        }
        expect(payload).toEqual({
          content: "合并后的正文",
          expected_source_version: 2,
        });
        version = 3;
        return HttpResponse.json({
          language: "zh-CN",
          content: payload.content,
          source_version: version,
          edited_by_user: true,
          updated_at: "2026-08-22T10:05:00.000000Z",
        });
      }),
    );

    renderAt(`${ROUTE_PATH}?tab=transcript`);
    fireEvent.click(await screen.findByRole("button", { name: "编辑正文" }));
    const editor = screen.getByRole("textbox", {
      name: "Transcript 正文编辑器",
    });
    fireEvent.change(editor, { target: { value: "我的草稿" } });
    version = 2;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(transcriptGets).toBeGreaterThan(1));
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

  it("完成任务不再把重试次数显示为完成进度", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          jobsResponse({
            status: "SUCCEEDED",
            progress: 1,
            attempts: 1,
            max_attempts: 3,
            error_code: null,
            retryable: false,
          }),
        ),
      ),
      http.get(`${DETAIL_URL}/transcript`, () =>
        HttpResponse.json({
          status: "READY",
          transcript: {
            language: "zh-CN",
            content: "已完成的转写正文",
            source_version: 1,
            edited_by_user: false,
            updated_at: "2026-08-23T12:00:00.000000Z",
          },
        }),
      ),
    );

    renderAt(`${ROUTE_PATH}?tab=transcript`);

    expect(await screen.findByText("100%")).toBeVisible();
    expect(screen.getByText("已完成")).toBeVisible();
    expect(screen.queryByText(/已完成.*1\/3/)).not.toBeInTheDocument();
  });
});
