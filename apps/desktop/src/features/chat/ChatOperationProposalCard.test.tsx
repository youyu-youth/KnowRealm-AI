// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatOperationProposalCard } from "./ChatOperationProposalCard";

const {
  confirmProposal,
  rejectProposal,
  listProposals,
  get,
  listOperations,
  undoOperation,
} = vi.hoisted(() => ({
  confirmProposal: vi.fn(),
  rejectProposal: vi.fn(),
  listProposals: vi.fn(),
  get: vi.fn(),
  listOperations: vi.fn(),
  undoOperation: vi.fn(),
}));

vi.mock("@/features/library/api/library", () => ({
  libraryApi: {
    confirmProposal,
    rejectProposal,
    listProposals,
  },
}));

vi.mock("@/features/settings/api/operationHistory", () => ({
  operationHistoryApi: { listOperations, undoOperation },
}));

vi.mock("@/features/courses/api/courses", () => ({
  courseApi: { get },
}));

// 组件级测试没有 RouterProvider：仅把 Link 降级为普通锚点，其余 router 导出保持原样。
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    Link: ({
      to,
      children,
    }: {
      to?: unknown;
      children?: ReactNode;
      params?: unknown;
    }) => <a href={typeof to === "string" ? to : "#"}>{children}</a>,
  };
});

const SESSION_ID = "session-1";

const SCHOOL_PAYLOAD = {
  name: "高中物理",
  learning_context: "SCHOOL",
  education_stage: "HIGH_SCHOOL",
  depth: null,
  course_type: null,
  description: null,
};

function proposalFixture(
  overrides: Partial<{
    id: string;
    status: string;
    session_id: string | null;
    error_code: string | null;
    result: Record<string, string> | null;
    proposal_type: string;
    payload: Record<string, unknown>;
  }> = {},
) {
  return {
    id: "p-1",
    proposal_type: "COURSE_CREATE",
    status: "PENDING",
    session_id: SESSION_ID,
    payload: SCHOOL_PAYLOAD,
    result: null,
    error_code: null,
    ...overrides,
  };
}

/** 确认路径回写的 operation 行（proposal_id 关联，工单 06 补充）。 */
function operationFixture(
  overrides: Partial<{
    id: string;
    action: string;
    proposal_id: string | null;
    status: string;
    undoable: boolean;
    undo_reason: string | null;
    undone_by: string | null;
  }> = {},
) {
  return {
    id: "op-1",
    run_id: null,
    proposal_id: "p-1",
    action: "update_library_item",
    level: "L1",
    target_type: "library_item",
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
    finished_at: "2026-09-28T08:00:01.000000Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listProposals.mockResolvedValue([]);
  listOperations.mockResolvedValue([]);
  get.mockResolvedValue({ id: "course-1", name: "Python 学习" });
});

describe("ChatOperationProposalCard", () => {
  it("恢复查询无提案时不渲染", () => {
    const { container } = renderWithQuery(
      <ChatOperationProposalCard sessionId={SESSION_ID} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("完整参数预览：读提案 payload 并把枚举值翻译为中文", async () => {
    listProposals.mockResolvedValue([proposalFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("高中物理")).toBeVisible();
    expect(screen.getByText("学业学习")).toBeVisible();
    expect(screen.getByText("高中")).toBeVisible();
    // 可选字段缺省时不渲染空行。
    expect(screen.queryByText("课程类型（可选）")).not.toBeInTheDocument();
  });

  it("确认调用 confirm 并转回执态、提供课程入口", async () => {
    confirmProposal.mockResolvedValue({
      ...proposalFixture(),
      status: "APPLIED",
      result: { course_id: "course-9" },
    });
    listProposals.mockResolvedValue([proposalFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认创建课程" }),
    );
    expect(await screen.findByText("课程已创建。")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开课程" });
    expect(link).toHaveAttribute("href", "/spaces/$courseId");
  });

  it("拒绝调用 reject 且不创建课程", async () => {
    rejectProposal.mockResolvedValue({
      ...proposalFixture(),
      status: "REJECTED",
    });
    listProposals.mockResolvedValue([proposalFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "拒绝创建课程" }),
    );
    await waitFor(() => {
      expect(rejectProposal).toHaveBeenCalledWith("p-1");
    });
    expect(await screen.findByText("已拒绝，未创建课程。")).toBeVisible();
    expect(confirmProposal).not.toHaveBeenCalled();
  });

  it("断线/重启后经既有提案查询恢复本会话待确认提案", async () => {
    listProposals.mockResolvedValue([proposalFixture({ id: "p-r1" })]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(
      await screen.findByRole("button", { name: "确认创建课程" }),
    ).toBeEnabled();
    expect(listProposals).toHaveBeenCalledWith({ session_id: SESSION_ID });
  });

  it("重启后恢复 APPLIED 回执与课程入口（不依赖组件内存）", async () => {
    listProposals.mockResolvedValue([
      proposalFixture({
        id: "p-a1",
        status: "APPLIED",
        result: { course_id: "course-7" },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("课程已创建。")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开课程" });
    expect(link).toHaveAttribute("href", "/spaces/$courseId");
    expect(confirmProposal).not.toHaveBeenCalled();
  });

  it("重启后恢复 FAILED：失败原因可读且确认按钮保留（重试）", async () => {
    listProposals.mockResolvedValue([
      proposalFixture({
        id: "p-f1",
        status: "FAILED",
        error_code: "COURSE_EDUCATION_STAGE_REQUIRED",
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("课程创建未完成");
    expect(alert).toHaveTextContent("学业场景必须选择教育阶段");
    // FAILED 可再确认：重试成功后转回执态。
    confirmProposal.mockResolvedValue({
      ...proposalFixture({ id: "p-f1" }),
      status: "APPLIED",
      result: { course_id: "course-3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认创建课程" }));
    expect(await screen.findByText("课程已创建。")).toBeVisible();
  });

  it("重启后恢复 REJECTED 终态文案且无操作按钮", async () => {
    listProposals.mockResolvedValue([
      proposalFixture({ id: "p-x1", status: "REJECTED" }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("已拒绝，未创建课程。")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "确认创建课程" }),
    ).not.toBeInTheDocument();
  });

  it("其他会话的恢复提案不渲染", async () => {
    listProposals.mockResolvedValue([
      proposalFixture({ id: "p-r2", session_id: "session-2" }),
    ]);
    const { container } = renderWithQuery(
      <ChatOperationProposalCard sessionId={SESSION_ID} />,
    );
    await screen.findByText("课程创建提案").catch(() => undefined);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});

function textRecordFixture(
  overrides: Partial<{
    id: string;
    status: string;
    session_id: string | null;
    error_code: string | null;
    result: Record<string, string | null> | null;
  }> = {},
) {
  return {
    id: "p-t1",
    proposal_type: "TEXT_RECORD_ADD",
    status: "PENDING",
    session_id: SESSION_ID,
    payload: {
      course_id: "course-1",
      content: "三角函数积分变换笔记：换元法与分部积分的适用边界。",
    },
    result: null,
    error_code: null,
    ...overrides,
  };
}

describe("ChatOperationProposalCard — TEXT_RECORD_ADD（工单 03）", () => {
  it("确认卡：目标课程名（既有课程 API）+ 正文摘要 + 明示将尝试生成 AI 总结", async () => {
    get.mockResolvedValue({ id: "course-1", name: "Python 学习" });
    listProposals.mockResolvedValue([textRecordFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("Python 学习")).toBeVisible();
    expect(
      screen.getByText("三角函数积分变换笔记：换元法与分部积分的适用边界。"),
    ).toBeVisible();
    expect(screen.getByText("保存后将尝试生成 AI 总结。")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认保存记录" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "拒绝保存记录" })).toBeEnabled();
  });

  it("确认调用 confirm 转回执态：记录入口 + 总结任务已提交", async () => {
    get.mockResolvedValue({ id: "course-1", name: "Python 学习" });
    confirmProposal.mockResolvedValue({
      ...textRecordFixture(),
      status: "APPLIED",
      result: {
        record_id: "rec-9",
        summary_job_id: "job-1",
        summary_error_code: null,
      },
    });
    listProposals.mockResolvedValue([textRecordFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认保存记录" }),
    );
    expect(await screen.findByText("记录已保存。")).toBeVisible();
    expect(screen.getByText("总结任务已提交，正在生成。")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开记录" });
    expect(link).toHaveAttribute("href", "/records/$recordId");
  });

  it("回执三态如实区分：未触发 ≠ 提交失败（恢复视图读 result 投影）", async () => {
    listProposals.mockResolvedValue([
      textRecordFixture({
        id: "p-n1",
        status: "APPLIED",
        result: {
          record_id: "rec-1",
          summary_job_id: null,
          summary_error_code: null,
        },
      }),
      textRecordFixture({
        id: "p-n2",
        status: "APPLIED",
        result: {
          record_id: "rec-2",
          summary_job_id: null,
          summary_error_code: "TEXT_RECORD_ADD_SUMMARY_ENQUEUE_FAILED",
        },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findAllByText("记录已保存。")).toHaveLength(2);
    expect(
      screen.getByText("未触发 AI 总结（AI 服务未配置或未同意外发）。"),
    ).toBeVisible();
    expect(
      screen.getByText(
        "总结任务提交失败（文本记录的总结任务提交失败），可在记录页重试。",
      ),
    ).toBeVisible();
  });

  it("重启后恢复 FAILED：失败原因可读且确认按钮保留（重试）", async () => {
    get.mockResolvedValue({ id: "course-1", name: "Python 学习" });
    listProposals.mockResolvedValue([
      textRecordFixture({
        id: "p-f1",
        status: "FAILED",
        error_code: "COURSE_ARCHIVED",
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("记录保存未完成");
    expect(alert).toHaveTextContent("归档课程不能接受新资料");
    expect(screen.getByRole("button", { name: "确认保存记录" })).toBeEnabled();
  });

  it("目标课程已不可读时确认卡如实提示", async () => {
    get.mockRejectedValue(new Error("404"));
    listProposals.mockResolvedValue([textRecordFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("课程已不可用")).toBeVisible();
  });
});

function courseUpdateFixture(
  overrides: Partial<{
    id: string;
    proposal_type: string;
    status: string;
    session_id: string | null;
    error_code: string | null;
    payload: Record<string, unknown>;
    snapshot: Record<string, unknown> | null;
    result: Record<string, unknown> | null;
  }> = {},
) {
  return {
    id: "p-u1",
    proposal_type: "OP_COURSE_UPDATE",
    status: "PENDING",
    session_id: SESSION_ID,
    payload: {
      course_id: "course-1",
      name: "Python 进阶",
      learning_context: null,
      education_stage: null,
      depth: null,
      course_type: null,
      description: null,
    },
    snapshot: {
      updated_at: "2026-09-21T08:00:00",
      name: "Python 学习",
      status: "ACTIVE",
      learning_context: "INTEREST",
      education_stage: null,
      depth: "INTERMEDIATE",
      course_type: null,
      description: null,
    },
    result: null,
    error_code: null,
    ...overrides,
  };
}

describe("ChatOperationProposalCard — 修改与归档动作（工单 03'）", () => {
  it("OP_COURSE_UPDATE 预览：目标课程 + before/after（旧值删除线）", async () => {
    listProposals.mockResolvedValue([courseUpdateFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("Python 进阶")).toBeVisible();
    // 目标行与 before 旧值同文本（快照名）：各出现一次，其中旧值带删除线。
    const mentions = screen.getAllByText("Python 学习");
    expect(mentions).toHaveLength(2);
    expect(mentions[1]).toHaveClass("line-through");
    expect(screen.getByText("目标课程")).toBeVisible();
  });

  it("OP_COURSE_UPDATE 确认转回执：修改结果 + 课程入口", async () => {
    confirmProposal.mockResolvedValue({
      ...courseUpdateFixture(),
      status: "APPLIED",
      result: {
        course_id: "course-1",
        before: { name: "Python 学习" },
        after: { name: "Python 进阶" },
      },
    });
    listProposals.mockResolvedValue([courseUpdateFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认修改课程" }),
    );
    expect(await screen.findByText("课程已修改。")).toBeVisible();
    expect(screen.getByRole("link", { name: "打开课程" })).toBeVisible();
  });

  it("快照失效 FAILED：提示重新提案，不允许确认原提案", async () => {
    listProposals.mockResolvedValue([
      courseUpdateFixture({
        status: "FAILED",
        error_code: "OPERATION_SNAPSHOT_STALE",
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("课程修改未完成");
    expect(alert).toHaveTextContent("目标已发生变化，提案已失效");
    expect(alert).toHaveTextContent("请在对话中重新提出操作并预览新提案");
    expect(alert).not.toHaveTextContent("可重新确认");
    expect(
      screen.queryByRole("button", { name: "确认修改课程" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "拒绝修改课程" })).toBeEnabled();
  });

  it("OP_COURSE_ARCHIVE 预览：目标课程 + 影响提示行", async () => {
    listProposals.mockResolvedValue([
      courseUpdateFixture({
        id: "p-a1",
        proposal_type: "OP_COURSE_ARCHIVE",
        payload: { course_id: "course-1" },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("Python 学习")).toBeVisible();
    expect(
      screen.getByText(
        "归档后课程保留全部数据，但不再接受新资料；之后可恢复。",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "确认归档课程" })).toBeEnabled();
  });

  it("OP_LIBRARY_ITEM_UPDATE 预览：目标条目 + 标题 before/after + 归类课程名", async () => {
    get.mockResolvedValue({ id: "course-2", name: "目标课程" });
    listProposals.mockResolvedValue([
      courseUpdateFixture({
        id: "p-i1",
        proposal_type: "OP_LIBRARY_ITEM_UPDATE",
        payload: {
          item_id: "item-1",
          title: "新标题",
          course_id: "course-2",
        },
        snapshot: {
          updated_at: "2026-09-21T08:00:00",
          title: "生命周期条目",
          course_id: null,
          status: "ACTIVE",
        },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    // 目标行与标题 before 旧值同文本：各一次，其中旧值带删除线。
    const mentions = await screen.findAllByText("生命周期条目");
    expect(mentions).toHaveLength(2);
    expect(mentions[1]).toHaveClass("line-through");
    expect(screen.getByText("新标题")).toBeVisible();
    expect(await screen.findByText("目标课程")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认修改条目" })).toBeEnabled();
  });
});

function deleteMoveFixture(
  overrides: Partial<{
    id: string;
    proposal_type: string;
    status: string;
    session_id: string | null;
    error_code: string | null;
    payload: Record<string, unknown>;
    snapshot: Record<string, unknown> | null;
    result: Record<string, unknown> | null;
  }> = {},
) {
  return {
    id: "p-d1",
    proposal_type: "OP_RECORD_SOFT_DELETE",
    status: "PENDING",
    session_id: SESSION_ID,
    payload: { record_id: "rec-1" },
    snapshot: {
      updated_at: "2026-09-21T08:00:00",
      title: "第 1 讲 一致性哈希",
      status: "COMPLETED",
      course_id: "course-1",
      knowledge_point_count: 2,
      quiz_count: 1,
      todo_count: 0,
      review_material_count: 0,
      has_summary: true,
    },
    result: null,
    error_code: null,
    ...overrides,
  };
}

describe("ChatOperationProposalCard — 删除与跨课迁移（工单 04）", () => {
  it("OP_RECORD_SOFT_DELETE 预览：目标记录 + 资产计数 + 不可逆警告", async () => {
    listProposals.mockResolvedValue([deleteMoveFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("第 1 讲 一致性哈希")).toBeVisible();
    expect(screen.getByText("有总结 · 知识点 2 条 · 习题 1 道")).toBeVisible();
    expect(
      screen.getByText(
        "删除后该记录及其全部记录级资产（总结、知识点、习题、Todo、复习资料）将一并移除，不可恢复。",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "确认删除记录" })).toBeEnabled();
  });

  it("OP_RECORD_SOFT_DELETE 预览：没有总结时明确显示", async () => {
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        snapshot: {
          title: "无总结记录",
          has_summary: false,
          knowledge_point_count: 0,
          quiz_count: 0,
          todo_count: 0,
          review_material_count: 0,
        },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("无总结")).toBeVisible();
  });

  it("OP_RECORD_SOFT_DELETE 确认转回执：无目标入口（记录已删除）", async () => {
    confirmProposal.mockResolvedValue({
      ...deleteMoveFixture(),
      status: "APPLIED",
      result: { record_id: "rec-1", title: "第 1 讲 一致性哈希" },
    });
    listProposals.mockResolvedValue([deleteMoveFixture()]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认删除记录" }),
    );
    expect(await screen.findByText("记录已删除。")).toBeVisible();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("OP_COURSE_SOFT_DELETE 预览：完整记录清单 + 级联警告", async () => {
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-c1",
        proposal_type: "OP_COURSE_SOFT_DELETE",
        payload: { course_id: "course-1" },
        snapshot: {
          updated_at: "2026-09-21T08:00:00",
          name: "Python 学习",
          status: "ACTIVE",
          records: Array.from({ length: 6 }, (_, index) => ({
            record_id: `rec-${index + 1}`,
            title: `第 ${index + 1} 讲`,
          })),
          record_count: 6,
        },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("Python 学习")).toBeVisible();
    expect(
      screen.getByText(
        "将一并删除 6 条记录：第 1 讲、第 2 讲、第 3 讲、第 4 讲、第 5 讲、第 6 讲",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "确认删除课程" })).toBeEnabled();
  });

  it("OP_COURSE_SOFT_DELETE 确认转回执：计数如实呈现", async () => {
    confirmProposal.mockResolvedValue({
      ...deleteMoveFixture({
        id: "p-c1",
        proposal_type: "OP_COURSE_SOFT_DELETE",
        payload: { course_id: "course-1" },
      }),
      status: "APPLIED",
      result: { course_id: "course-1", record_count: 2 },
    });
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-c1",
        proposal_type: "OP_COURSE_SOFT_DELETE",
        payload: { course_id: "course-1" },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认删除课程" }),
    );
    expect(
      await screen.findByText("课程已删除（含 2 条记录）。"),
    ).toBeVisible();
  });

  it("OP_RECORD_MOVE_COURSE 预览：记录 + 课程 before/after + 语义提示", async () => {
    get.mockResolvedValue({ id: "course-9", name: "分布式系统" });
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-m1",
        proposal_type: "OP_RECORD_MOVE_COURSE",
        payload: { record_id: "rec-1", target_course_id: "course-9" },
        snapshot: {
          updated_at: "2026-09-21T08:00:00",
          title: "第 1 讲 一致性哈希",
          status: "COMPLETED",
          course_id: "course-1",
        },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    expect(await screen.findByText("第 1 讲 一致性哈希")).toBeVisible();
    expect(await screen.findByText("分布式系统")).toBeVisible();
    expect(screen.getByText("所属课程")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认迁移记录" })).toBeEnabled();
  });

  it("OP_RECORD_MOVE_COURSE 确认转回执：记录入口跳转", async () => {
    get.mockResolvedValue({ id: "course-9", name: "分布式系统" });
    confirmProposal.mockResolvedValue({
      ...deleteMoveFixture({
        id: "p-m1",
        proposal_type: "OP_RECORD_MOVE_COURSE",
        payload: { record_id: "rec-1", target_course_id: "course-9" },
      }),
      status: "APPLIED",
      result: {
        record_id: "rec-1",
        before_course_id: "course-1",
        after_course_id: "course-9",
      },
    });
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-m1",
        proposal_type: "OP_RECORD_MOVE_COURSE",
        payload: { record_id: "rec-1", target_course_id: "course-9" },
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "确认迁移记录" }),
    );
    expect(await screen.findByText("记录已迁移。")).toBeVisible();
    const link = screen.getByRole("link", { name: "打开记录" });
    expect(link).toHaveAttribute("href", "/records/$recordId");
  });

  it("APPLIED 回执行呈现撤销入口：点击调撤销端点（工单 06 补充）", async () => {
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-u1",
        proposal_type: "OP_LIBRARY_ITEM_UPDATE",
        payload: { item_id: "item-1", title: "java 高级教程928" },
        status: "APPLIED",
        result: { item_id: "item-1" },
      }),
    ]);
    listOperations.mockResolvedValue([
      operationFixture({ id: "op-u1", proposal_id: "p-u1" }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("条目已修改。")).toBeVisible();
    const undoButton = screen.getByRole("button", { name: "撤销" });
    expect(undoButton).toBeVisible();
    undoOperation.mockResolvedValue(operationFixture({ id: "comp-1" }));
    fireEvent.click(undoButton);
    await waitFor(() => expect(undoOperation).toHaveBeenCalledWith("op-u1"));
  });

  it("已撤销的回执行显示标记不显示按钮；无关联 operation 行不渲染入口", async () => {
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-u1",
        proposal_type: "OP_LIBRARY_ITEM_UPDATE",
        payload: { item_id: "item-1", title: "java 高级教程928" },
        status: "APPLIED",
        result: { item_id: "item-1" },
      }),
      deleteMoveFixture({
        id: "p-u2",
        proposal_type: "OP_LIBRARY_ITEM_ARCHIVE",
        payload: { item_id: "item-2" },
        status: "APPLIED",
        result: { item_id: "item-2" },
      }),
    ]);
    // p-u1 已撤销（undone_by 非空）；p-u2 无关联行（历史数据/查询缺席）。
    listOperations.mockResolvedValue([
      operationFixture({
        id: "op-u1",
        proposal_id: "p-u1",
        undone_by: "comp-1",
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);

    expect(await screen.findByText("条目已修改。")).toBeVisible();
    expect(screen.getByText("该操作已撤销。")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "撤销" }),
    ).not.toBeInTheDocument();
  });

  it("不可撤销的回执行就地呈现原因（spec 用户故事 28，创建类无按钮）", async () => {
    listProposals.mockResolvedValue([
      deleteMoveFixture({
        id: "p-text",
        proposal_type: "TEXT_RECORD_ADD",
        payload: { course_id: "c-1", content: "新特性" },
        status: "APPLIED",
        result: { record_id: "r-1" },
      }),
    ]);
    // 保存文本记录＝创建类动作：undoable=false＋注册项声明的原因。
    listOperations.mockResolvedValue([
      operationFixture({
        id: "op-text",
        action: "add_text_record_to_course",
        proposal_id: "p-text",
        undoable: false,
        undo_reason: "创建类动作不在首批撤销范围，如需移除请在记录页手动删除",
      }),
    ]);
    renderWithQuery(<ChatOperationProposalCard sessionId={SESSION_ID} />);

    expect(
      await screen.findByText(
        "不可撤销：创建类动作不在首批撤销范围，如需移除请在记录页手动删除",
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "撤销" }),
    ).not.toBeInTheDocument();
  });
});
