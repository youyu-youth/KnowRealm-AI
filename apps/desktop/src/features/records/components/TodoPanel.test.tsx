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

const completedRecord: RecordOut = {
  ...record,
  status: "COMPLETED",
  summary_confirmed_at: "2026-08-24T12:00:00.000000Z",
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
    // 详情页渲染会写路由记忆偏好；回显请求键模拟部分更新的合并语义。
    http.put(
      `${TEST_SIDECAR_URL}/api/settings/preferences`,
      async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          theme: "SYSTEM",
          font_scale: "M",
          timezone: null,
          close_behavior: "TRAY",
          quick_note_shortcut: "Ctrl+Alt+N",
          autostart: false,
          quiz_last_count: 5,
          last_route: null,
          ...body,
        });
      },
    ),
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

describe("Todo 页签", () => {
  const TODOS_URL = `${DETAIL_URL}/todos`;

  function todoOut(
    overrides: Partial<components["schemas"]["TodoOut"]> = {},
  ): components["schemas"]["TodoOut"] {
    return {
      id: "66666666-6666-4666-8666-666666666666",
      record_id: RECORD_ID,
      batch_id: null,
      content: "复习进程调度",
      status: "TODO",
      source: "MANUAL",
      generated_from_summary_id: null,
      generation_status: null,
      sort_order: 0,
      created_at: "2026-08-25T12:00:00.000000Z",
      updated_at: "2026-08-25T12:00:00.000000Z",
      ...overrides,
    };
  }

  function todoReadOut(
    overrides: Partial<components["schemas"]["TodoReadOut"]> = {},
  ): components["schemas"]["TodoReadOut"] {
    return {
      items: [],
      action_required: "NONE",
      active_job_id: null,
      blocked_reason: null,
      ...overrides,
    };
  }

  it("生成候选后可修剪并整批采纳", async () => {
    const candidate = todoOut({
      batch_id: JOB_ID,
      content: "复习调度算法",
      source: "AI",
      generated_from_summary_id: "55555555-5555-4555-8555-555555555555",
      generation_status: "DRAFT",
    });
    let data = todoReadOut({ action_required: "GENERATE" });
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () => HttpResponse.json(data)),
      http.post(`${DETAIL_URL}/todo-jobs`, () => {
        data = todoReadOut({ items: [candidate], action_required: "ADOPT" });
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
      http.patch(`${TODOS_URL}/${candidate.id}`, async ({ request }) => {
        const body: unknown = await request.json();
        if (
          typeof body !== "object" ||
          body === null ||
          !("content" in body) ||
          typeof body.content !== "string"
        ) {
          throw new Error("Todo 编辑请求体不符合契约");
        }
        candidate.content = body.content;
        return HttpResponse.json(candidate);
      }),
      http.post(`${DETAIL_URL}/todo-batches/${JOB_ID}/confirmations`, () => {
        candidate.generation_status = "ACTIVE";
        data = todoReadOut({ items: [candidate], action_required: "GENERATE" });
        return HttpResponse.json(data);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    fireEvent.click(
      await screen.findByRole("button", { name: "生成 Todo 建议" }),
    );
    expect(
      await screen.findByRole("heading", { name: "待审阅建议" }),
    ).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "编辑待办 复习调度算法" }),
    );
    fireEvent.change(screen.getByLabelText("编辑待办内容"), {
      target: { value: "复习并对比调度算法" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("复习并对比调度算法")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "采纳候选" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "待审阅建议" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("checkbox", { name: "复习并对比调度算法" }),
    ).toBeVisible();
  });

  it("失败态可重试，候选可整批丢弃", async () => {
    const candidate = todoOut({
      batch_id: JOB_ID,
      source: "AI",
      generated_from_summary_id: "55555555-5555-4555-8555-555555555555",
      generation_status: "DRAFT",
    });
    let data = todoReadOut({ action_required: "RETRY" });
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () => HttpResponse.json(data)),
      http.post(`${DETAIL_URL}/todo-jobs`, () => {
        data = todoReadOut({ items: [candidate], action_required: "ADOPT" });
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
      http.post(`${DETAIL_URL}/todo-batches/${JOB_ID}/discards`, () => {
        data = todoReadOut({ action_required: "GENERATE" });
        return HttpResponse.json(data);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(await screen.findByText("上次生成没有成功")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
    expect(
      await screen.findByRole("heading", { name: "待审阅建议" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "丢弃候选" }));
    expect(
      await screen.findByRole("button", { name: "生成 Todo 建议" }),
    ).toBeVisible();
  });

  it("总结换代时禁止采纳旧候选，并给出丢弃重生成指引", async () => {
    const candidate = todoOut({
      batch_id: JOB_ID,
      source: "AI",
      generated_from_summary_id: "55555555-5555-4555-8555-555555555555",
      generation_status: "DRAFT",
    });
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(
          todoReadOut({
            items: [candidate],
            blocked_reason: "SUMMARY_SUPERSEDED",
          }),
        ),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(await screen.findByText(/总结已更新，请丢弃旧候选/)).toBeVisible();
    expect(screen.getByRole("button", { name: "采纳候选" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "丢弃候选" })).toBeEnabled();
  });

  it("Provider 缺失时指引前往配置入口", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(
          todoReadOut({ blocked_reason: "PROVIDER_NOT_CONFIGURED" }),
        ),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(
      await screen.findByRole("button", { name: "前往 Provider 配置" }),
    ).toBeVisible();
  });

  it("未完成记录页签禁用，完成后未确认总结时空态指引去总结页签", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(TODOS_URL, () => HttpResponse.json(todoReadOut())),
    );
    renderAt(ROUTE_PATH);

    const todoTab = await screen.findByRole("tab", { name: "Todo" });
    expect(todoTab).toHaveAttribute("aria-disabled", "true");

    cleanup();
    window.history.replaceState(null, "", "/");
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(
          todoReadOut({ blocked_reason: "SUMMARY_NOT_CONFIRMED" }),
        ),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(
      await screen.findByRole("heading", {
        name: "先确认总结，再生成待办建议",
      }),
    ).toBeVisible();
    // 手动记账不受门控限制：空态指引之外仍提供新增表单
    expect(screen.getByLabelText("新增待办内容")).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "查看总结" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("未同意外发的空态可一键授权并恢复", async () => {
    let granted = false;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(
          granted
            ? todoReadOut()
            : todoReadOut({ blocked_reason: "CONSENT_REQUIRED" }),
        ),
      ),
      http.post(LLM_CONSENT_URL, () => {
        granted = true;
        return HttpResponse.json({ ok: true });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(
      await screen.findByRole("heading", { name: "需要同意外部 AI 处理" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "同意外部 AI 处理" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "需要同意外部 AI 处理" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("新增待办内容")).toBeEnabled();
  });

  it("勾选完成划线弱化、取消勾选恢复，行内编辑与删除即时生效", async () => {
    const itemA = todoOut();
    const itemB = todoOut({
      id: "77777777-7777-4777-8777-777777777777",
      content: "补课后作业",
      sort_order: 1,
    });
    let items = [itemA, itemB];
    const toggleBodies: unknown[] = [];
    const patchBodies: unknown[] = [];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(todoReadOut({ items: [...items] })),
      ),
      http.post(`${TODOS_URL}/${itemA.id}/toggles`, async ({ request }) => {
        const body: unknown = await request.json();
        if (
          typeof body !== "object" ||
          body === null ||
          !("status" in body) ||
          (body.status !== "TODO" && body.status !== "DONE")
        ) {
          throw new Error("Todo 状态请求体不符合契约");
        }
        const status = body.status;
        toggleBodies.push(body);
        items = items.map((item) =>
          item.id === itemA.id ? { ...item, status } : item,
        );
        return HttpResponse.json(items[0]);
      }),
      http.patch(`${TODOS_URL}/${itemB.id}`, async ({ request }) => {
        patchBodies.push(await request.json());
        items = items.map((item) =>
          item.id === itemB.id
            ? { ...item, content: "补完课后作业并订正" }
            : item,
        );
        return HttpResponse.json(items[1]);
      }),
      http.delete(`${TODOS_URL}/${itemB.id}`, () => {
        items = items.filter((item) => item.id !== itemB.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(await screen.findByText("复习进程调度")).toBeVisible();
    expect(screen.getByText("补课后作业")).toBeVisible();

    // 勾选完成 → 划线弱化原位保留
    fireEvent.click(screen.getByRole("checkbox", { name: "复习进程调度" }));
    await waitFor(() =>
      expect(
        screen.getByText("复习进程调度", { selector: "span" }),
      ).toHaveClass("line-through"),
    );
    expect(toggleBodies).toEqual([{ status: "DONE" }]);

    // 取消勾选恢复未完成态
    fireEvent.click(screen.getByRole("checkbox", { name: "复习进程调度" }));
    await waitFor(() =>
      expect(
        screen.getByText("复习进程调度", { selector: "span" }),
      ).not.toHaveClass("line-through"),
    );

    // 行内编辑保存新内容
    fireEvent.click(
      screen.getByRole("button", { name: "编辑待办 补课后作业" }),
    );
    const editor = screen.getByLabelText("编辑待办内容");
    expect(editor).toHaveValue("补课后作业");
    fireEvent.change(editor, { target: { value: "补完课后作业并订正" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(screen.getByText("补完课后作业并订正")).toBeVisible(),
    );
    expect(patchBodies).toEqual([{ content: "补完课后作业并订正" }]);

    // 删除后条目消失
    fireEvent.click(
      screen.getByRole("button", { name: "删除待办 补完课后作业并订正" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("补完课后作业并订正")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("复习进程调度")).toBeVisible();
  });

  it("blocked 下清单照常可用，新增待办追加在列表尾部", async () => {
    const itemA = todoOut();
    let items = [itemA];
    const createBodies: unknown[] = [];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(TODOS_URL, () =>
        HttpResponse.json(
          todoReadOut({
            items: [...items],
            blocked_reason: "SUMMARY_NOT_CONFIRMED",
          }),
        ),
      ),
      http.post(TODOS_URL, async ({ request }) => {
        createBodies.push(await request.json());
        const created = todoOut({
          id: "88888888-8888-4888-8888-888888888888",
          content: "查参考资料",
          sort_order: items.length,
        });
        items = [...items, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=todo`);

    expect(await screen.findByText("复习进程调度")).toBeVisible();
    // 有条目时不显示 blocked 空态，但手动记账照常可用
    expect(
      screen.queryByRole("heading", { name: "先确认总结，再生成待办建议" }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("新增待办内容"), {
      target: { value: "查参考资料" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    await waitFor(() => expect(screen.getByText("查参考资料")).toBeVisible());
    expect(createBodies).toEqual([{ content: "查参考资料" }]);
    expect(screen.getByLabelText("新增待办内容")).toHaveValue("");
    // 新条目排在既有条目之后
    expect(
      screen.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual(["复习进程调度", "查参考资料"]);
  });
});
