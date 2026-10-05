// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { AgentRunProgress } from "./AgentRunProgress";
import { agentKeys } from "@/features/agent/api/authMode";
import { libraryKeys } from "@/features/library/api/keys";
import { libraryApi } from "@/features/library/api/library";

const { getRun, listProposals } = vi.hoisted(() => ({
  getRun: vi.fn(),
  listProposals: vi.fn(),
}));

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

vi.mock("@/features/library/api/library", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/features/library/api/library")>();
  return { ...actual, libraryApi: { ...actual.libraryApi, listProposals } };
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
  listProposals.mockResolvedValue([]);
});

/** 挂在 sessionProposals 查询上的探针（模拟聊天视图里的提案卡消费者）。 */
function ProposalProbe() {
  useQuery({
    queryKey: libraryKeys.sessionProposals("sess-1"),
    queryFn: () => libraryApi.listProposals({ session_id: "sess-1" }),
  });
  return null;
}

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

  it("Run 翻终态时失效本会话提案查询（草案卡即时可见，07 review 六轮 P1）", async () => {
    getRun.mockResolvedValue(runData({ status: "RUNNING", finished_at: null }));
    const { queryClient } = renderWithQuery(
      <>
        <AgentRunProgress runId="run-1" />
        <ProposalProbe />
      </>,
    );
    // 活动态轮询中：提案查询仅探针挂载拉取一次。
    expect(await screen.findByText("进行中")).toBeInTheDocument();
    await waitFor(() => expect(listProposals).toHaveBeenCalledTimes(1));
    // 轮询观察到终态（以缓存翻转模拟）：提案查询被失效并重取——用户停留
    // 当前聊天即可见后台落出的确认卡（如 PLAN_DRAFT 草案卡）。
    act(() => {
      queryClient.setQueryData(
        agentKeys.runDetail("run-1"),
        runData({ status: "COMPLETED" }),
      );
    });
    expect(await screen.findByText("已完成")).toBeInTheDocument();
    await waitFor(() => expect(listProposals).toHaveBeenCalledTimes(2));
  });

  it("挂载即终态也失效提案查询（首查竞态兜底，07 review 十轮 P1）", async () => {
    // 场景：挂载时恰逢草案落库提交——提案首查读到旧列表（尚无草案）、Run
    // 首查已返回 COMPLETED。翻转检测（先观察到活动态）在此不成立且终态
    // 停轮询，进入终态本身即须失效一次。
    getRun.mockResolvedValue(runData({ status: "COMPLETED" }));
    renderWithQuery(
      <>
        <AgentRunProgress runId="run-1" />
        <ProposalProbe />
      </>,
    );
    expect(await screen.findByText("已完成")).toBeInTheDocument();
    await waitFor(() => expect(listProposals).toHaveBeenCalledTimes(2));
  });
});
