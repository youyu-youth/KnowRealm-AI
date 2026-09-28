// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatBatchPlanCard } from "./ChatBatchPlanCard";

const {
  listProposals,
  confirmProposal,
  rejectProposal,
  getRun,
  resumeRun,
  retryRunOperation,
  cancelRun,
} = vi.hoisted(() => ({
  listProposals: vi.fn(),
  confirmProposal: vi.fn(),
  rejectProposal: vi.fn(),
  getRun: vi.fn(),
  resumeRun: vi.fn(),
  retryRunOperation: vi.fn(),
  cancelRun: vi.fn(),
}));

vi.mock("@/features/library/api/library", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/features/library/api/library")>();
  return {
    ...actual,
    libraryApi: {
      ...actual.libraryApi,
      listProposals,
      confirmProposal,
      rejectProposal,
    },
  };
});

vi.mock("@/features/settings/api/operationHistory", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/settings/api/operationHistory")
    >();
  return {
    ...actual,
    operationHistoryApi: {
      ...actual.operationHistoryApi,
      getRun,
      resumeRun,
      retryRunOperation,
      cancelRun,
    },
  };
});

const SESSION_ID = "sess-1";

function planProposal(overrides: Record<string, unknown> = {}) {
  return {
    id: "plan-1",
    proposal_type: "OP_BATCH",
    status: "PENDING",
    session_id: SESSION_ID,
    message_id: "msg-1",
    target_type: null,
    target_id: null,
    payload: {
      items: [
        {
          action: "update_library_item",
          item_id: "item-1",
          course_id: "course-1",
        },
        { action: "archive_library_item", item_id: "item-2", depends_on: [0] },
      ],
      plan_version: 1,
      auth_mode: "REQUEST_APPROVAL",
      instruction_text: "把这些条目归到课程 X",
    },
    snapshot: {
      plan_version: 1,
      items: [
        {
          action: "update_library_item",
          item_id: "item-1",
          state: { title: "条目一" },
        },
        {
          action: "archive_library_item",
          item_id: "item-2",
          state: { title: "条目二" },
        },
      ],
    },
    result: null,
    error_code: null,
    created_at: "2026-09-26T08:00:00.000000Z",
    ...overrides,
  };
}

function runDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    session_id: SESSION_ID,
    auth_mode: "REQUEST_APPROVAL",
    instruction_text: "把这些条目归到课程 X",
    proposal_id: "plan-1",
    status: "RUNNING",
    plan: { plan_version: 1, items: [] },
    plan_version: 1,
    waiting_reason: null,
    cancel_requested: false,
    created_at: "2026-09-26T08:00:00.000000Z",
    updated_at: "2026-09-26T08:00:00.000000Z",
    finished_at: null,
    operations: [
      {
        id: "op-1",
        run_id: "run-1",
        proposal_id: "plan-1",
        action: "update_library_item",
        level: "L1",
        target_type: "library_item",
        target_id: "item-1",
        payload: { item_id: "item-1", course_id: "course-1" },
        snapshot: { title: "条目一" },
        authorization: {
          auth_mode: "REQUEST_APPROVAL",
          trigger: "USER_CONFIRMED_PROPOSAL",
        },
        status: "SUCCEEDED",
        attempts: 1,
        result: { item_id: "item-1" },
        error_code: null,
        undo_of: null,
        undone_by: null,
        created_at: "2026-09-26T08:00:00.000000Z",
        updated_at: "2026-09-26T08:00:00.000000Z",
        finished_at: "2026-09-26T08:00:01.000000Z",
      },
      {
        id: "op-2",
        run_id: "run-1",
        proposal_id: "plan-1",
        action: "archive_library_item",
        level: "L1",
        target_type: "library_item",
        target_id: "item-2",
        payload: { item_id: "item-2" },
        snapshot: { title: "条目二" },
        authorization: {
          auth_mode: "REQUEST_APPROVAL",
          trigger: "USER_CONFIRMED_PROPOSAL",
        },
        status: "PLANNED",
        attempts: 1,
        result: null,
        error_code: null,
        undo_of: null,
        undone_by: null,
        created_at: "2026-09-26T08:00:00.000000Z",
        updated_at: "2026-09-26T08:00:00.000000Z",
        finished_at: null,
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listProposals.mockResolvedValue([]);
});

describe("ChatBatchPlanCard", () => {
  it("计划卡逐项列出目标与参数、计划版本，整卡确认走提案确认接口", async () => {
    listProposals.mockResolvedValue([planProposal()]);
    confirmProposal.mockResolvedValue(planProposal({ status: "APPLIED" }));
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("批量整理计划")).toBeInTheDocument();
    expect(screen.getByText("共 2 项")).toBeInTheDocument();
    expect(screen.getByText("计划版本 v1")).toBeInTheDocument();
    // 逐项目标名取确认卡预览投影（提交时固化的快照标题）。
    expect(screen.getByText("条目一")).toBeInTheDocument();
    expect(screen.getByText("条目二")).toBeInTheDocument();
    expect(screen.getByText("修改资料条目")).toBeInTheDocument();
    expect(screen.getByText("归档资料条目")).toBeInTheDocument();
    expect(screen.getByText("依赖第 1 项")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认执行本计划" }));
    await waitFor(() => {
      expect(confirmProposal).toHaveBeenCalledWith("plan-1");
    });
  });

  it("计划修改后版本递增并提示需重新确认", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        payload: { ...planProposal().payload, plan_version: 2 },
        snapshot: { ...planProposal().snapshot, plan_version: 2 },
      }),
    ]);
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("计划版本 v2")).toBeInTheDocument();
    expect(
      screen.getByText("计划已更新，需重新确认后才执行"),
    ).toBeInTheDocument();
  });

  it("拒绝计划：不动业务事实（只调拒绝接口）", async () => {
    listProposals.mockResolvedValue([planProposal()]);
    rejectProposal.mockResolvedValue(planProposal({ status: "REJECTED" }));
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: "拒绝" }));
    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("plan-1");
    });
    expect(confirmProposal).not.toHaveBeenCalled();
  });

  it("确认后就地转任务进度：逐项结果与显式动作按钮", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        status: "APPLIED",
        result: { run_id: "run-1", plan_version: 1, item_count: 2 },
      }),
    ]);
    getRun.mockResolvedValue(
      runDetail({
        status: "WAITING_USER",
        waiting_reason: "OPERATION_SNAPSHOT_STALE",
        operations: [
          { ...runDetail().operations[0] },
          {
            ...runDetail().operations[1],
            status: "FAILED",
            error_code: "OPERATION_SNAPSHOT_STALE",
            finished_at: "2026-09-26T08:00:05.000000Z",
          },
        ],
      }),
    );
    resumeRun.mockResolvedValue(runDetail());
    retryRunOperation.mockResolvedValue(runDetail());
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("等待用户")).toBeInTheDocument();
    expect(screen.getByText(/等待处理：目标已发生变化/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => {
      expect(retryRunOperation).toHaveBeenCalledWith("run-1", "op-2");
    });
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    await waitFor(() => {
      expect(resumeRun).toHaveBeenCalledWith("run-1");
    });
  });

  it("快照失效的计划卡隐藏确认按钮（需重新预览授权）", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        status: "FAILED",
        error_code: "OPERATION_SNAPSHOT_STALE",
      }),
    ]);
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认执行本计划" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeInTheDocument();
  });

  it("推进中可取消任务（取消不冒充撤销）", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        status: "APPLIED",
        result: { run_id: "run-1", plan_version: 1, item_count: 2 },
      }),
    ]);
    getRun.mockResolvedValue(runDetail());
    cancelRun.mockResolvedValue(runDetail({ status: "CANCELLED" }));
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: "取消任务" }));
    await waitFor(() => {
      expect(cancelRun).toHaveBeenCalledWith("run-1");
    });
  });
});
