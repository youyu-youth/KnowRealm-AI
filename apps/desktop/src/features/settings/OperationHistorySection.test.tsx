// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { OperationHistorySection } from "./OperationHistorySection";

const {
  listRuns,
  getRun,
  deleteRun,
  purgeFinished,
  listOperations,
  listActivity,
} = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  deleteRun: vi.fn(),
  purgeFinished: vi.fn(),
  listOperations: vi.fn(),
  listActivity: vi.fn(),
}));

vi.mock("@/features/settings/api/operationHistory", () => ({
  operationHistoryApi: {
    listRuns,
    getRun,
    deleteRun,
    purgeFinished,
    listOperations,
    listActivity,
  },
}));

function operationData(overrides: Record<string, unknown> = {}) {
  return {
    id: "op-1",
    run_id: null,
    proposal_id: "proposal-1",
    action: "create_course",
    level: "L1",
    target_type: null,
    target_id: null,
    payload: { name: "高中物理" },
    snapshot: null,
    authorization: {
      auth_mode: "REQUEST_APPROVAL",
      trigger: "USER_CONFIRMED_PROPOSAL",
    },
    status: "SUCCEEDED",
    attempts: 1,
    attempts_json: null,
    result: { course_id: "c-12345678" },
    error_code: null,
    undo_of: null,
    undone_by: null,
    created_at: "2026-09-22T08:00:00.000000Z",
    updated_at: "2026-09-22T08:00:00.000000Z",
    finished_at: "2026-09-22T08:00:00.000000Z",
    ...overrides,
  };
}

function runData(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    session_id: "sess-1",
    auth_mode: "REQUEST_APPROVAL",
    instruction_text: "把这些条目都归到课程 X",
    proposal_id: null,
    status: "COMPLETED",
    plan: null,
    plan_version: 1,
    waiting_reason: null,
    cancel_requested: false,
    created_at: "2026-09-22T08:00:00.000000Z",
    updated_at: "2026-09-22T08:00:00.000000Z",
    finished_at: "2026-09-22T08:10:00.000000Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRuns.mockResolvedValue([]);
  listOperations.mockResolvedValue([]);
  listActivity.mockResolvedValue([]);
});

describe("OperationHistorySection", () => {
  it("展示单步操作条目（动作/目标/状态）与任务、审计空态", async () => {
    listOperations.mockResolvedValue([operationData()]);
    renderWithQuery(<OperationHistorySection />);
    expect(
      await screen.findByRole("heading", { name: "操作历史" }),
    ).toBeInTheDocument();
    // 单步操作条目：动作翻译 + 载荷目标名 + 状态。
    expect(await screen.findByText("创建课程")).toBeInTheDocument();
    expect(screen.getByText("高中物理")).toBeInTheDocument();
    expect(screen.getByText("已成功")).toBeInTheDocument();
    // 任务与审计本阶段空态。
    expect(screen.getByText(/暂无任务记录/)).toBeInTheDocument();
    expect(screen.getByText("暂无模式切换记录。")).toBeInTheDocument();
  });

  it("任务列表展开显示逐操作", async () => {
    listRuns.mockResolvedValue([runData()]);
    getRun.mockResolvedValue({
      ...runData(),
      operations: [operationData({ id: "op-r1", run_id: "run-1" })],
    });
    renderWithQuery(<OperationHistorySection />);
    expect(
      await screen.findByText("把这些条目都归到课程 X"),
    ).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "展开或收起任务的逐项操作" }),
    );
    expect(await screen.findByText("创建课程")).toBeInTheDocument();
    expect(getRun).toHaveBeenCalledWith("run-1");
  });

  it("批量清理：二次确认后调用清理并失效重取", async () => {
    listOperations
      .mockResolvedValueOnce([operationData()])
      .mockResolvedValue([]);
    purgeFinished.mockResolvedValue({ runs_deleted: 0, operations_deleted: 1 });
    renderWithQuery(<OperationHistorySection />);
    await screen.findByText("高中物理");
    fireEvent.click(screen.getByRole("button", { name: /清理已结束任务/ }));
    expect(
      await screen.findByRole("heading", { name: "清理已结束任务的历史？" }),
    ).toBeInTheDocument();
    // 未确认不触发请求。
    expect(purgeFinished).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /^清理$/ }));
    await waitFor(() => {
      expect(purgeFinished).toHaveBeenCalled();
    });
    // 清理成功后列表失效重取为空。
    await waitFor(() => {
      expect(screen.getByText(/暂无操作记录/)).toBeInTheDocument();
    });
  });

  it("单任务删除经二次确认后调用 DELETE 并失效重取", async () => {
    listRuns.mockResolvedValueOnce([runData()]).mockResolvedValue([]);
    deleteRun.mockResolvedValue(undefined);
    renderWithQuery(<OperationHistorySection />);
    await screen.findByText("把这些条目都归到课程 X");
    fireEvent.click(screen.getByRole("button", { name: "删除该任务的历史" }));
    // 二次确认：未确认不触发请求。
    expect(
      await screen.findByRole("heading", { name: "删除该任务的历史？" }),
    ).toBeInTheDocument();
    expect(deleteRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /^删除$/ }));
    await waitFor(() => {
      expect(deleteRun).toHaveBeenCalledWith("run-1");
    });
    await waitFor(() => {
      expect(screen.getByText(/暂无任务记录/)).toBeInTheDocument();
    });
  });

  it("单任务删除后同时失效任务与单步操作列表（后端 FK 级联删其操作）", async () => {
    listRuns.mockResolvedValueOnce([runData()]).mockResolvedValue([]);
    listOperations
      .mockResolvedValueOnce([operationData()])
      .mockResolvedValue([]);
    deleteRun.mockResolvedValue(undefined);
    renderWithQuery(<OperationHistorySection />);
    await screen.findByText("把这些条目都归到课程 X");
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(listOperations).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "删除该任务的历史" }));
    fireEvent.click(await screen.findByRole("button", { name: /^删除$/ }));
    await waitFor(() => {
      expect(deleteRun).toHaveBeenCalledWith("run-1");
    });
    await waitFor(() => {
      expect(listRuns).toHaveBeenCalledTimes(2);
      expect(listOperations).toHaveBeenCalledTimes(2);
    });
  });

  it("失败操作展示错误码", async () => {
    listOperations.mockResolvedValue([
      operationData({
        id: "op-f",
        action: "add_text_record_to_course",
        status: "FAILED",
        error_code: "COURSE_NOT_FOUND",
        result: null,
        payload: { course_id: "c-1", content: "x" },
      }),
    ]);
    renderWithQuery(<OperationHistorySection />);
    expect(await screen.findByText("添加文本记录")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("COURSE_NOT_FOUND")).toBeInTheDocument();
  });
});
