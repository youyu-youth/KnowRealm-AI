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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const ROUTE_PATH = `/records/${RECORD_ID}`;
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const SUMMARY_CONFIRM_URL = `${DETAIL_URL}/summary-confirmations`;
const KNOWLEDGE_POINTS_URL = `${DETAIL_URL}/knowledge-points`;
const KNOWLEDGE_POINT_JOBS_URL = `${DETAIL_URL}/knowledge-point-jobs`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const LLM_CONSENT_URL = `${TEST_SIDECAR_URL}/api/settings/external-processing-consents/llm`;

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

function readKnowledgePointWriteRequest(
  body: unknown,
): components["schemas"]["KnowledgePointWriteRequest"] {
  if (
    typeof body !== "object" ||
    body === null ||
    !("name" in body) ||
    typeof body.name !== "string" ||
    !("detail" in body) ||
    typeof body.detail !== "string" ||
    !("tags" in body) ||
    !Array.isArray(body.tags) ||
    !body.tags.every((tag) => typeof tag === "string") ||
    !("importance" in body) ||
    typeof body.importance !== "number"
  ) {
    throw new Error("知识点写入请求体不符合契约");
  }
  return {
    name: body.name,
    detail: body.detail,
    tags: body.tags,
    importance: body.importance,
  };
}

function activateKnowledgePoint(
  item: components["schemas"]["KnowledgePointOut"],
): components["schemas"]["KnowledgePointOut"] {
  return { ...item, generation_status: "ACTIVE" };
}

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

describe("KnowledgePointPanel", () => {
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
      await screen.findByRole("heading", { name: "未配置 AI 服务" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "前往设置" })).toBeVisible();
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
        const body = readKnowledgePointWriteRequest(await request.json());
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
        createdBody = readKnowledgePointWriteRequest(await request.json());
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
            ? draftItems.map(activateKnowledgePoint)
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
            items: draftItems.map(activateKnowledgePoint),
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

  it("转写换代后已保存知识点保持可编辑且重新生成入口锁定", async () => {
    const itemId = "44444444-4444-4444-8444-444444444444";
    let items: components["schemas"]["KnowledgePointOut"][] = [
      draftKnowledgePoint({ generation_status: "ACTIVE" }),
    ];
    server.use(
      // 换代后 Record 回 SUMMARY_PENDING，知识点页签仍可见可选
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "SUMMARY_PENDING" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items,
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: "SUMMARY_SUPERSEDED",
          input_mode: null,
        }),
      ),
      http.patch(`${KNOWLEDGE_POINTS_URL}/${itemId}`, async ({ request }) => {
        const body = readKnowledgePointWriteRequest(await request.json());
        items = items.map((item) =>
          item.id === itemId ? { ...item, ...body } : item,
        );
        return HttpResponse.json(items.find((item) => item.id === itemId));
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    const tab = await screen.findByRole("tab", { name: "知识点" });
    expect(tab).toBeEnabled();
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(
      await screen.findByRole("heading", { name: "转写已修改，总结需要更新" }),
    ).toBeVisible();
    expect(
      screen.getByText(/已保存的知识点不受影响；待新总结确认后/),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "前往 Summary" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "生成候选知识点" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "进程调度" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "编辑 进程调度" }));
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "换代中的编辑" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    expect(
      await screen.findByRole("heading", { name: "换代中的编辑" }),
    ).toBeVisible();
  });

  it("换代后确认被禁用并引导丢弃，新总结确认后重新生成恢复", async () => {
    let stage: "blocked" | "discarded" | "unlocked" = "blocked";
    let jobSubmitted = false;
    const pendingSummary: components["schemas"]["SummaryOut"] = {
      id: "55555555-5555-4555-8555-555555555555",
      record_id: RECORD_ID,
      version_no: 2,
      transcript_source_version: 2,
      topic: "进程调度（第二代）",
      abstract: "转写修订后的第二代总结摘要。",
      sections: [
        { heading: "调度", points: ["调度器按修订后的策略选择进程。"] },
      ],
      status: "GENERATED",
      model: "qwen-plus",
      prompt_version: "summary-v1",
      user_feedback: null,
      created_at: "2026-08-24T13:00:00.000000Z",
    };
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          ...record,
          status: stage === "unlocked" ? "COMPLETED" : "SUMMARY_PENDING",
        }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () => {
        if (stage === "blocked") {
          return HttpResponse.json({
            items: [draftKnowledgePoint()],
            action_required: "NONE",
            active_job_id: null,
            blocked_reason: "SUMMARY_SUPERSEDED",
            input_mode: null,
          });
        }
        if (stage === "discarded") {
          return HttpResponse.json({
            items: [],
            action_required: "NONE",
            active_job_id: null,
            blocked_reason: "SUMMARY_SUPERSEDED",
            input_mode: null,
          });
        }
        return HttpResponse.json({
          items: [],
          action_required: "GENERATE",
          active_job_id: jobSubmitted ? JOB_ID : null,
          blocked_reason: null,
          input_mode: null,
        });
      }),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          summary: pendingSummary,
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
        }),
      ),
      http.post(SUMMARY_CONFIRM_URL, () => {
        stage = "unlocked";
        return HttpResponse.json({
          summary: { ...pendingSummary, status: "CONFIRMED" },
          record_status: "COMPLETED",
        });
      }),
      http.post(
        `${DETAIL_URL}/knowledge-point-batches/${JOB_ID}/discards`,
        () => {
          stage = "discarded";
          return HttpResponse.json({
            items: [],
            action_required: "NONE",
            active_job_id: null,
            blocked_reason: "SUMMARY_SUPERSEDED",
            input_mode: null,
          });
        },
      ),
      http.post(KNOWLEDGE_POINT_JOBS_URL, () => {
        jobSubmitted = true;
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    expect(
      await screen.findByRole("heading", { name: "候选知识点" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "确认保存" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "丢弃整批" })).toBeEnabled();
    expect(
      screen.getByRole("heading", { name: "转写已修改，总结需要更新" }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "丢弃整批" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "丢弃整批" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("heading", { name: "候选知识点" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "转写已修改，总结需要更新" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "生成候选知识点" }),
    ).not.toBeInTheDocument();

    // 在 Summary 页签确认新总结后，回到知识点页签重新生成入口已恢复
    fireEvent.click(screen.getByRole("button", { name: "前往 Summary" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认总结" }));
    fireEvent.click(screen.getByRole("tab", { name: "知识点" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "生成候选知识点" }),
    );
    expect(
      await screen.findByRole("heading", { name: "正在生成知识点" }),
    ).toBeVisible();
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
        const body = readKnowledgePointWriteRequest(await request.json());
        items = items.map((item) =>
          item.id === itemId ? { ...item, ...body } : item,
        );
        return HttpResponse.json(items.find((item) => item.id === itemId));
      }),
      http.post(KNOWLEDGE_POINTS_URL, async ({ request }) => {
        const body = readKnowledgePointWriteRequest(await request.json());
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

  it("点击知识点创建挂载对话并预填建议问题", async () => {
    const sessionId = "88888888-8888-4888-8888-888888888888";
    let createBody: unknown;
    const item = draftKnowledgePoint({ generation_status: "ACTIVE" });
    const chatSession: components["schemas"]["ChatSessionOut"] = {
      id: sessionId,
      mode: "ASK",
      title: null,
      record_id: RECORD_ID,
      course_id: COURSE_ID,
      record_deleted: false,
      created_at: "2026-08-29T08:00:00.000000Z",
      updated_at: "2026-08-29T08:00:00.000000Z",
    };
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "COMPLETED" }),
      ),
      http.get(KNOWLEDGE_POINTS_URL, () =>
        HttpResponse.json({
          items: [item],
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          input_mode: null,
        }),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions`,
        async ({ request }) => {
          createBody = await request.json();
          return HttpResponse.json(chatSession, { status: 201 });
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([chatSession]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${sessionId}`, () =>
        HttpResponse.json(chatSession),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${sessionId}/messages`,
        () => HttpResponse.json([]),
      ),
      http.get(LLM_PROVIDER_URL, () =>
        HttpResponse.json({
          provider: {
            base_url: "https://stub.example.com/v1",
            model: "stub-chat-model",
            has_api_key: true,
            api_key_hint: "sk-…test",
          },
        }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    fireEvent.click(await screen.findByRole("button", { name: "进程调度" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${sessionId}`),
    );
    expect(createBody).toEqual({
      mode: "ASK",
      record_id: RECORD_ID,
      knowledge_point_id: item.id,
    });
    expect(
      await screen.findByRole("textbox", { name: "提问输入框" }),
    ).toHaveValue("给我讲讲「进程调度」");
    expect(screen.getByRole("button", { name: "发送" })).toBeEnabled();
  });
});
