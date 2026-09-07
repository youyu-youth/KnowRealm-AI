// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
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
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const CONFIRM_URL = `${DETAIL_URL}/summary-confirmations`;
const TODAY_URL = `${TEST_SIDECAR_URL}/api/today/pending-summaries`;

const todo = {
  record_id: RECORD_ID,
  title: "操作系统第一讲",
  course_id: COURSE_ID,
  course_name: "操作系统",
  ready_at: "2026-08-23T12:00:00.000000Z",
};

const generatedSummary = {
  id: "44444444-4444-4444-8444-444444444444",
  record_id: RECORD_ID,
  version_no: 1,
  status: "GENERATED",
  transcript_source_version: 1,
  topic: "进程调度",
  abstract: "调度器按照既定策略选择下一个获得处理器的进程。",
  sections: [{ heading: "核心机制", points: ["就绪队列决定候选顺序。"] }],
  prompt_version: "summary-v1",
  model: "qwen-plus",
  user_feedback: null,
  created_at: "2026-08-23T10:00:00Z",
};

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
        action_required: "NONE",
        active_job_id: null,
        blocked_reason: null,
        summary: null,
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

describe("今日页", () => {
  it("列出待确认总结并直达对应记录", async () => {
    server.use(
      http.get(TODAY_URL, () => HttpResponse.json([todo])),
      http.get(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学习记录不存在或已删除" },
          { status: 404 },
        ),
      ),
    );
    renderAt();

    const link = await screen.findByRole("link", { name: /操作系统第一讲/ });
    expect(link).toHaveAttribute("href", `/records/${RECORD_ID}`);
    expect(screen.getByText("操作系统")).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "待确认总结列表" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();
  });

  it("无待办时不显示空态文案，读取失败可重试", async () => {
    renderAt();
    expect(await screen.findByText("学习趋势")).toBeInTheDocument();
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();

    cleanup();
    let calls = 0;
    server.use(
      http.get(TODAY_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json([todo]);
      }),
    );
    renderAt();
    expect(
      await screen.findByRole(
        "heading",
        { name: "今日待办暂时无法读取" },
        {
          timeout: 6_000,
        },
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    ).toBeInTheDocument();
    // 统计带并入今日页后，本用例叠加了图表渲染与重试退避，超出默认 5s。
  }, 20_000);

  it("确认总结后返回今日页，待办立即移除", async () => {
    let confirmed = false;
    let confirmCalls = 0;
    server.use(
      http.get(TODAY_URL, () => HttpResponse.json(confirmed ? [] : [todo])),
      http.get(DETAIL_URL, () =>
        HttpResponse.json({
          id: RECORD_ID,
          course_id: null,
          capture_type: "DOCUMENT_IMPORT",
          title: "操作系统第一讲",
          status: confirmed ? "COMPLETED" : "SUMMARY_READY",
          duration_ms: 0,
          summary_confirmed_at: confirmed
            ? "2026-08-23T12:05:00.000000Z"
            : null,
          created_at: "2026-08-19T08:30:00.000000Z",
          updated_at: "2026-08-23T12:00:00.000000Z",
        }),
      ),
      http.get(SUMMARY_URL, () =>
        HttpResponse.json({
          action_required: "NONE",
          active_job_id: null,
          blocked_reason: null,
          summary: {
            ...generatedSummary,
            status: confirmed ? "CONFIRMED" : "GENERATED",
          },
        }),
      ),
      http.post(CONFIRM_URL, async ({ request }) => {
        confirmCalls += 1;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        expect(await request.json()).toEqual({
          summary_id: generatedSummary.id,
        });
        confirmed = true;
        return HttpResponse.json({
          summary: { ...generatedSummary, status: "CONFIRMED" },
          record_status: "COMPLETED",
        });
      }),
    );
    renderAt();

    fireEvent.click(
      await screen.findByRole("link", { name: /操作系统第一讲/ }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "确认总结" }));
    expect(await screen.findByText("AI 总结 · 已确认")).toBeInTheDocument();
    expect(confirmCalls).toBe(1);

    window.history.back();
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: /操作系统第一讲/ }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();
  });
});
