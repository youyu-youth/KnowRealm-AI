// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ResearchSessionDialog } from "./ResearchSessionDialog";

const mocks = vi.hoisted(() => ({
  available: true,
  mutate: vi.fn(),
  listCourses: vi.fn(),
}));

vi.mock("@/features/chat/useCreateChatSession", () => ({
  useCreateChatSession: () => ({
    mutate: mocks.mutate,
    isPending: false,
    error: null,
  }),
}));

vi.mock("@/features/chat/useWebSearchAvailability", () => ({
  useWebSearchAvailability: () => mocks.available,
}));

vi.mock("@/features/courses/api/courses", () => ({
  courseApi: {
    list: mocks.listCourses,
  },
}));

const COURSES = [
  { id: "course-1", name: "操作系统" },
  { id: "course-2", name: "线性代数" },
];

function openDialog() {
  renderWithQuery(<ResearchSessionDialog open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.available = true;
  mocks.listCourses.mockResolvedValue(COURSES);
});

describe("ResearchSessionDialog", () => {
  it("弹窗三件：研究问题输入、范围默认全部资料、联网默认开启", () => {
    openDialog();
    expect(screen.getByLabelText("研究问题")).toHaveValue("");
    expect(screen.getByRole("radio", { name: /全部资料/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /指定课程/ })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "联网搜索" })).toBeChecked();
    expect(screen.getByRole("button", { name: "开始研究" })).toBeDisabled();
  });

  it("研究问题必填：填写后确认可用，提交携带 RESEARCH 模式与研究问题", () => {
    openDialog();
    fireEvent.change(screen.getByLabelText("研究问题"), {
      target: { value: "注意力机制变体的取舍" },
    });
    const submit = screen.getByRole("button", { name: "开始研究" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    expect(mocks.mutate).toHaveBeenCalledWith(
      {
        mode: "RESEARCH",
        scope: "ALL",
        prompt: "注意力机制变体的取舍",
      },
      expect.anything(),
    );
  });

  it("选指定课程时必须选课；填问题选课后提交携带 course_id", async () => {
    openDialog();
    fireEvent.click(screen.getByRole("radio", { name: /指定课程/ }));
    expect(screen.getByRole("button", { name: "开始研究" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("研究问题"), {
      target: { value: "进程调度算法对比" },
    });
    // 未选课（清单加载后也不自动选）仍不可提交。
    await screen.findByRole("radio", { name: "操作系统" });
    fireEvent.click(screen.getByRole("button", { name: "开始研究" }));
    expect(mocks.mutate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("radio", { name: "操作系统" }));
    fireEvent.click(screen.getByRole("button", { name: "开始研究" }));
    await waitFor(() => {
      expect(mocks.mutate).toHaveBeenCalledWith(
        {
          mode: "RESEARCH",
          scope: "COURSE",
          course_id: "course-1",
          prompt: "进程调度算法对比",
        },
        expect.anything(),
      );
    });
  });

  it("纯联网范围提交 FREE，不携带 course_id", () => {
    openDialog();
    fireEvent.change(screen.getByLabelText("研究问题"), {
      target: { value: "某个时效性问题" },
    });
    fireEvent.click(screen.getByRole("radio", { name: /纯联网/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始研究" }));
    expect(mocks.mutate).toHaveBeenCalledWith(
      {
        mode: "RESEARCH",
        scope: "FREE",
        prompt: "某个时效性问题",
      },
      expect.anything(),
    );
  });

  it("无搜索 key：明示降级提示且联网开关置灰", () => {
    mocks.available = false;
    openDialog();
    const webSwitch = screen.getByRole("switch", { name: "联网搜索" });
    // Base UI Switch 渲染 button，disabled 以 aria-disabled 呈现（B1 已知坑）。
    expect(webSwitch).toHaveAttribute("aria-disabled", "true");
    expect(webSwitch).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByText("未配置搜索供应商，本次研究会话仅能使用本地资料。"),
    ).toBeVisible();
  });
});
