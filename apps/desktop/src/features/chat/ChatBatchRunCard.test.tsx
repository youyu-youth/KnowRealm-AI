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

function operation(runId: string, overrides: Record<string, unknown> = {}) {
  return {
    id: `op-${runId}`,
    run_id: runId,
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
    ...overrides,
  };
}

function detail(
  runId: string,
  overrides: Record<string, unknown> = {},
  opOverrides: Record<string, unknown> = {},
) {
  return {
    ...run({ id: runId, ...overrides }),
    operations: [operation(runId, opOverrides)],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRuns.mockResolvedValue([]);
  getRun.mockImplementation((runId: string) => Promise.resolve(detail(runId)));
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

  it("已结束任务保留为终态回执（工单 05 review）；计划卡任务不在本面板", async () => {
    getRun.mockImplementation((runId: string) =>
      Promise.resolve(detail(runId, { status: "COMPLETED" })),
    );
    listRuns.mockResolvedValue([
      run({ id: "run-approved", proposal_id: "plan-1" }),
      run({ id: "run-done", status: "COMPLETED" }),
    ]);
    renderWithQuery(<ChatBatchRunCard sessionId={SESSION_ID} />);

    // 终态回执在聊天内可见（不再只剩设置页操作历史），且为终态形态（无取消按钮）。
    expect(await screen.findByText("Agent 任务")).toBeInTheDocument();
    expect(await screen.findByText("已完成")).toBeInTheDocument();
    await waitFor(() => {
      expect(getRun).toHaveBeenCalledWith("run-done");
    });
    expect(
      screen.queryByRole("button", { name: "取消任务" }),
    ).not.toBeInTheDocument();
    // 计划卡批准的任务归计划卡：不查询、不呈现。
    expect(getRun).not.toHaveBeenCalledWith("run-approved");
  });

  it("活跃任务排前、终态回执排后（组内保持接口顺序）", async () => {
    getRun.mockImplementation((runId: string) =>
      Promise.resolve(
        detail(
          runId,
          {},
          { target_id: runId, snapshot: { title: `目标-${runId}` } },
        ),
      ),
    );
    listRuns.mockResolvedValue([
      // 接口倒序：终态任务创建更晚（回执不应盖住仍在跑的任务）。
      run({ id: "run-done", status: "COMPLETED" }),
      run({ id: "run-active", status: "RUNNING" }),
    ]);
    renderWithQuery(<ChatBatchRunCard sessionId={SESSION_ID} />);

    // 两个 Run 的详情查询各自异步落地：waitFor 重试到齐再比顺序。
    await waitFor(() => {
      const titles = screen
        .getAllByText(/^目标-/)
        .map((node) => node.textContent);
      expect(titles).toEqual(["目标-run-active", "目标-run-done"]);
    });
  });
});
