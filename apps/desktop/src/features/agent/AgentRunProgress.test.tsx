// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { AgentRunProgress } from "./AgentRunProgress";

const { getRun } = vi.hoisted(() => ({ getRun: vi.fn() }));

// 模块级工具（isRunActive 等）随实际实现保留，只替换 api 对象。
vi.mock("@/features/settings/api/operationHistory", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/settings/api/operationHistory")
    >();
  return {
    ...actual,
    operationHistoryApi: { getRun },
  };
});

function operationData(overrides: Record<string, unknown> = {}) {
  return {
    id: "op-1",
    run_id: "run-1",
    proposal_id: null,
    action: "update_library_item",
    level: "L1",
    target_type: null,
    target_id: null,
    payload: {},
    snapshot: null,
    authorization: null,
    status: "SUCCEEDED",
    attempts: 1,
    attempts_history: null,
    result: null,
    error_code: null,
    undoable: true,
    undo_reason: null,
    undo_of: null,
    undone_by: null,
    created_at: "2026-09-28T08:00:00.000000Z",
    updated_at: "2026-09-28T08:00:00.000000Z",
    finished_at: "2026-09-28T08:00:00.000000Z",
    ...overrides,
  };
}

function runData(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    session_id: "sess-1",
    auth_mode: "REQUEST_APPROVAL",
    instruction_text: "批量归类",
    proposal_id: null,
    status: "FAILED",
    plan: null,
    plan_version: 1,
    waiting_reason: null,
    cancel_requested: false,
    created_at: "2026-09-28T08:00:00.000000Z",
    updated_at: "2026-09-28T08:00:00.000000Z",
    finished_at: "2026-09-28T08:10:00.000000Z",
    operations: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getRun.mockResolvedValue(runData());
});

describe("AgentRunProgress", () => {
  it("补偿行不渲染重试按钮（失败补偿走重新发起撤销，不走正向重试）", async () => {
    getRun.mockResolvedValue(
      runData({
        operations: [
          operationData({
            id: "op-1",
            status: "FAILED",
            error_code: "OPERATION_SNAPSHOT_STALE",
          }),
          // 批次撤销失败留痕的 FAILED 补偿行（undo_of 挂原行）。
          operationData({
            id: "op-c1",
            status: "FAILED",
            error_code: "OPERATION_UNDO_CONFLICT",
            undo_of: "op-1",
          }),
        ],
      }),
    );
    renderWithQuery(<AgentRunProgress runId="run-1" />);
    // 仅正向失败行有一个「重试」按钮；补偿行的失败原因如实呈现（留痕可见）。
    expect(await screen.findAllByRole("button", { name: "重试" })).toHaveLength(
      1,
    );
    expect(screen.getByText("撤销补偿")).toBeInTheDocument();
    expect(
      screen.getByText(
        "目标在操作执行后已被修改，撤销被拒绝以避免覆盖后续修改",
      ),
    ).toBeInTheDocument();
  });

  it("不可撤销的成功步骤就地呈现原因（spec 用户故事 28，review P2）", async () => {
    getRun.mockResolvedValue(
      runData({
        operations: [
          operationData({
            id: "op-del",
            action: "delete_record",
            undoable: false,
            undo_reason:
              "记录删除不可撤销：删除会影响记录级资产与学习证据链，且暂无恢复入口",
          }),
        ],
      }),
    );
    renderWithQuery(<AgentRunProgress runId="run-1" />);
    expect(
      await screen.findByText(
        "不可撤销：记录删除不可撤销：删除会影响记录级资产与学习证据链，且暂无恢复入口",
      ),
    ).toBeInTheDocument();
  });
});
