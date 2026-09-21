// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ChatOperationProposalCard } from "./ChatOperationProposalCard";

const { confirmProposal, rejectProposal, listProposals, get } = vi.hoisted(
  () => ({
    confirmProposal: vi.fn(),
    rejectProposal: vi.fn(),
    listProposals: vi.fn(),
    get: vi.fn(),
  }),
);

vi.mock("@/features/library/api/library", () => ({
  libraryApi: {
    confirmProposal,
    rejectProposal,
    listProposals,
  },
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

beforeEach(() => {
  vi.clearAllMocks();
  listProposals.mockResolvedValue([]);
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
