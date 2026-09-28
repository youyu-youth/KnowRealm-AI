// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatBatchRunCard } from "./ChatBatchRunCard";

const { listRuns, getRun } = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
}));

vi.mock("@/features/settings/api/operationHistory", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/settings/api/operationHistory")
    >();
  return {
    ...actual,
    operationHistoryApi: { ...actual.operationHistoryApi, listRuns, getRun },
  };
});

const SESSION_ID = "sess-1";

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    session_id: SESSION_ID,
    auth_mode: "AUTO_APPROVE",
    instruction_text: "把这些条目都归档",
    proposal_id: null,
    status: "RUNNING",
    plan: { plan_version: 1, items: [] },
    plan_version: 1,
    waiting_reason: null,
    cancel_requested: false,
    created_at: "2026-09-26T08:00:00.000000Z",
    updated_at: "2026-09-26T08:00:00.000000Z",
    finished_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRuns.mockResolvedValue([]);
  getRun.mockResolvedValue({
    ...run(),
    operations: [
      {
        id: "op-1",
        run_id: "run-1",
        proposal_id: null,
        action: "archive_library_item",
        level: "L1",
        target_type: "library_item",
        target_id: "item-1",
        payload: { item_id: "item-1" },
        snapshot: { title: "条目一" },
        authorization: { auth_mode: "AUTO_APPROVE", trigger: "AUTO_EXECUTED" },
        status: "SUCCEEDED",
        attempts: 1,
        result: { item_id: "item-1", status: "ARCHIVED" },
        error_code: null,
        undo_of: null,
        undone_by: null,
        created_at: "2026-09-26T08:00:00.000000Z",
        updated_at: "2026-09-26T08:00:00.000000Z",
        finished_at: "2026-09-26T08:00:01.000000Z",
      },
    ],
  });
});

describe("ChatBatchRunCard", () => {
  it("呈现本会话未结束的档位直执行任务（逐项结果与进度）", async () => {
    listRuns.mockResolvedValue([run()]);
    renderWithQuery(<ChatBatchRunCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("Agent 任务")).toBeInTheDocument();
    // 详情查询异步落地：进度行与逐项结果随后呈现。
    expect(await screen.findByText("已完成 1/1 项")).toBeInTheDocument();
    expect(screen.getByText("归档资料条目")).toBeInTheDocument();
    expect(screen.getByText("条目一")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "取消任务" }),
    ).toBeInTheDocument();
  });

  it("经计划卡批准的任务与已结束任务不在本面板呈现（各归其位）", async () => {
    listRuns.mockResolvedValue([
      run({ id: "run-approved", proposal_id: "plan-1" }),
      run({ id: "run-done", status: "COMPLETED" }),
    ]);
    renderWithQuery(<ChatBatchRunCard sessionId={SESSION_ID} />);

    // 两条被过滤后列表为空：面板不渲染（已结束任务归操作历史、计划卡任务归计划卡）。
    await waitFor(() => {
      expect(listRuns).toHaveBeenCalled();
    });
    expect(screen.queryByText("Agent 任务")).not.toBeInTheDocument();
  });
});
