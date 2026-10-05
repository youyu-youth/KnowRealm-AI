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
  listCourses,
} = vi.hoisted(() => ({
  listProposals: vi.fn(),
  confirmProposal: vi.fn(),
  rejectProposal: vi.fn(),
  getRun: vi.fn(),
  resumeRun: vi.fn(),
  retryRunOperation: vi.fn(),
  cancelRun: vi.fn(),
  listCourses: vi.fn(),
}));

vi.mock("@/features/courses/api/courses", () => ({
  courseApi: { list: listCourses },
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
  listCourses.mockResolvedValue([{ id: "course-1", name: "高等数学" }]);
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
    // 授权参数可见：归类目标显示课程名，依赖显示计划内序号。
    expect(screen.getByText("归类到课程：高等数学")).toBeInTheDocument();
    expect(screen.getByText("依赖第 1 项")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认执行本计划" }));
    await waitFor(() => {
      expect(confirmProposal).toHaveBeenCalledWith("plan-1");
    });
  });

  it("授权参数完整可见：多依赖全部列出、课程名查不到时回落 id 缩写", async () => {
    const unknownCourseId = "99999999-aaaa-bbbb-cccc-dddddddddddd";
    listProposals.mockResolvedValue([
      planProposal({
        payload: {
          items: [
            {
              action: "update_library_item",
              item_id: "item-1",
              course_id: unknownCourseId,
            },
            { action: "archive_library_item", item_id: "item-2" },
            {
              action: "archive_library_item",
              item_id: "item-3",
              depends_on: [0, 1],
            },
          ],
          plan_version: 1,
          auth_mode: "REQUEST_APPROVAL",
          instruction_text: "把这些条目归档",
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
            {
              action: "archive_library_item",
              item_id: "item-3",
              state: { title: "条目三" },
            },
          ],
        },
      }),
    ]);
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(
      await screen.findByText(`归类到课程：#${unknownCourseId.slice(0, 8)}`),
    ).toBeInTheDocument();
    expect(screen.getByText("依赖第 1、2 项")).toBeInTheDocument();
    expect(screen.getByText("共 3 项")).toBeInTheDocument();
  });

  it("保存的建课导入计划含空值与输出引用，重新打开仍可展示授权参数", async () => {
    // 06 工单：course_id 等参数可为 {step, field} 引用对象（执行时后端注入）。
    // 真机曾因对引用对象取 id 缩写（.slice）崩溃到全局兜底页，此处钉回归。
    listProposals.mockResolvedValue([
      planProposal({
        payload: {
          items: [
            {
              action: "create_course",
              item_id: null,
              title: null,
              course_id: null,
              name: "Deep Agents 入门",
              learning_context: "CAREER",
              education_stage: null,
              depth: "BEGINNER",
              description: null,
              url: null,
              depends_on: [],
            },
            {
              action: "ingest_library_item",
              item_id: null,
              title: null,
              name: null,
              learning_context: null,
              education_stage: null,
              depth: null,
              description: null,
              url: "https://docs.langchain.com/oss/python/deepagents/customization#interpreters",
              course_id: { step: 0, field: "course_id" },
              depends_on: [0],
            },
          ],
          plan_version: 1,
          auth_mode: "REQUEST_APPROVAL",
          instruction_text: "建课并导入资料",
        },
        snapshot: {
          plan_version: 1,
          items: [
            { action: "create_course", item_id: null, state: {} },
            { action: "ingest_library_item", item_id: null, state: {} },
          ],
        },
      }),
    ]);
    const view = renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("共 2 项")).toBeInTheDocument();
    expect(screen.getByText("创建课程")).toBeInTheDocument();
    expect(screen.getByText("导入网页资料")).toBeInTheDocument();
    expect(screen.getByText("Deep Agents 入门")).toBeInTheDocument();
    expect(screen.getByText(/学习场景：职业技能/)).toBeInTheDocument();
    expect(screen.getByText(/学习深度：入门/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "https://docs.langchain.com/oss/python/deepagents/customization#interpreters",
      ),
    ).toBeInTheDocument();
    // 引用对象渲染为来源步骤（1 起序号，与依赖列同口径）。
    expect(screen.getByText("归类到课程：第 1 步的输出")).toBeInTheDocument();
    expect(screen.getByText("依赖第 1 项")).toBeInTheDocument();
    view.unmount();
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("Deep Agents 入门")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "确认执行本计划" }),
    ).toBeEnabled();
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

  it("多资料建课编排卡：四类来源与建目标、末步草案的动作及授权参数逐项可见", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        payload: {
          items: [
            {
              action: "create_course",
              name: "论文精读",
              learning_context: "CAREER",
              depth: "INTERMEDIATE",
            },
            {
              action: "create_goal",
              course_id: { step: 0, field: "course_id" },
              goal_type: "SKILL",
              target_date: "2026-11-01",
              daily_minutes: 60,
              target_score: 85,
            },
            { action: "ingest_library_item", url: "https://example.com/paper" },
            {
              action: "ingest_local_document",
              path: "D:\\papers\\attention.pdf",
            },
            {
              action: "add_text_record_to_course",
              content:
                "论文 A 的核心结论：注意力机制可并行化，长文本摘要同理。",
              course_id: { step: 0, field: "course_id" },
            },
            {
              action: "generate_plan_draft",
              goal_id: { step: 1, field: "goal_id" },
              depends_on: [3],
            },
          ],
          plan_version: 1,
          auth_mode: "REQUEST_APPROVAL",
          instruction_text: "把这几篇论文整理到新课程并生成学习计划",
        },
        snapshot: { plan_version: 1, items: [] },
      }),
    ]);
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("共 6 项")).toBeInTheDocument();
    // 四类来源与编排动作的授权要素逐项可见。
    expect(screen.getByText("创建课程")).toBeInTheDocument();
    expect(screen.getByText("创建学习目标")).toBeInTheDocument();
    expect(screen.getByText("导入网页资料")).toBeInTheDocument();
    expect(screen.getByText("导入本地文档")).toBeInTheDocument();
    expect(screen.getByText("添加文本记录")).toBeInTheDocument();
    expect(screen.getByText("生成学习计划草案")).toBeInTheDocument();
    // 目标参数（类型 / 期限 / 每日投入）与引用注入（建课 / 建目标输出）可见。
    expect(screen.getByText(/目标类型：技能掌握/)).toBeInTheDocument();
    expect(screen.getByText(/期限：2026-11-01/)).toBeInTheDocument();
    expect(screen.getByText(/每日投入：每天 60 分钟/)).toBeInTheDocument();
    expect(screen.getByText(/目标分数：85/)).toBeInTheDocument();
    expect(screen.getAllByText(/第 1 步的输出/).length).toBeGreaterThanOrEqual(
      2,
    );
    expect(screen.getByText(/目标：第 2 步的输出/)).toBeInTheDocument();
    // 本地路径与粘贴文本摘要是目标形态（不造假名）。
    expect(screen.getByText("D:\\papers\\attention.pdf")).toBeInTheDocument();
    expect(
      screen.getByText(
        "论文 A 的核心结论：注意力机制可并行化，长文本摘要同理。",
      ),
    ).toBeInTheDocument();
  });

  it("共享引用项显示源资料身份：快照 item_title 优先，无快照以资料 id 兜底（07 review 七轮 P1）", async () => {
    listProposals.mockResolvedValue([
      planProposal({
        payload: {
          items: [
            {
              action: "create_course",
              name: "论文精读",
              learning_context: "INTEREST",
              depth: "BEGINNER",
            },
            // 引用新课程：提交期快照跳过（_skip_item_snapshot），无源标题——
            // 此前渲染为空目标，多个共享来源无法核对。
            {
              action: "add_shared_ref",
              library_item_id: "b0000000-aaaa-4000-8000-0000000000f1",
              course_id: { step: 0, field: "course_id" },
            },
            // 归类既有课程：提交期快照固化 item_title（共享引用快照字段名）。
            {
              action: "add_shared_ref",
              library_item_id: "d2222222-bbbb-4000-8000-0000000000f2",
              course_id: "course-1",
            },
          ],
          plan_version: 1,
          auth_mode: "REQUEST_APPROVAL",
          instruction_text: "把这两份资料挂到新课程",
        },
        snapshot: {
          plan_version: 1,
          // 提交期快照按 index 对应：创建类含引用跳过、既有课程项固化 item_title。
          items: [{}, {}, { state: { item_title: "注意力机制综述" } }],
        },
      }),
    ]);
    renderWithQuery(<ChatBatchPlanCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("共 3 项")).toBeInTheDocument();
    // 快照源标题（item_title 字段）与资料 id 兜底都可见——多个共享来源可核对。
    expect(screen.getByText("注意力机制综述")).toBeInTheDocument();
    expect(screen.getByText("#b0000000")).toBeInTheDocument();
    expect(screen.getAllByText("添加共享引用").length).toBe(2);
  });
});
