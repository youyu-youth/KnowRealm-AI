// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { DataDirectorySection } from "./DataDirectorySection";

const {
  getDataDirectory,
  openDataDirectory,
  changeDataDirectory,
  chooseDataDirectory,
  listenMigrationProgress,
  relaunchApplication,
  exitApplication,
} = vi.hoisted(() => ({
  getDataDirectory: vi.fn(),
  openDataDirectory: vi.fn(),
  changeDataDirectory: vi.fn(),
  chooseDataDirectory: vi.fn(),
  listenMigrationProgress: vi.fn(),
  relaunchApplication: vi.fn(),
  exitApplication: vi.fn(),
}));

vi.mock("@/services/tauri/dataDirectory", () => ({
  getDataDirectory,
  openDataDirectory,
  changeDataDirectory,
  chooseDataDirectory,
  listenMigrationProgress,
}));

vi.mock("@/services/tauri/lifecycle", () => ({
  isDesktopLifecycleAvailable: () => true,
  relaunchApplication,
  exitApplication,
}));

function renderSection() {
  return renderWithQuery(<DataDirectorySection />);
}

async function openConfirmDialog(target = "D:\\KnowRealmNew") {
  await screen.findByDisplayValue("C:\\Users\\tester\\KnowRealm");
  chooseDataDirectory.mockResolvedValue(target);
  fireEvent.click(screen.getByRole("button", { name: "更改数据目录" }));
  expect(await screen.findByText("确认并迁移")).toBeInTheDocument();
  return target;
}

async function confirmAndFailWith(rejection: string) {
  changeDataDirectory.mockRejectedValue(rejection);
  renderSection();
  await openConfirmDialog();
  fireEvent.click(screen.getByRole("button", { name: "确认并迁移" }));
  return await screen.findAllByRole("alert");
}

describe("DataDirectorySection", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    getDataDirectory.mockReset();
    openDataDirectory.mockReset();
    changeDataDirectory.mockReset();
    chooseDataDirectory.mockReset();
    listenMigrationProgress.mockReset();
    relaunchApplication.mockReset();
    exitApplication.mockReset();
    listenMigrationProgress.mockResolvedValue(() => {});
    getDataDirectory.mockResolvedValue("C:\\Users\\tester\\KnowRealm");
  });

  it("展示当前数据目录并通过系统资源管理器打开", async () => {
    openDataDirectory.mockResolvedValue(undefined);

    renderSection();

    expect(
      await screen.findByDisplayValue("C:\\Users\\tester\\KnowRealm"),
    ).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "打开数据目录" }));

    await waitFor(() => expect(openDataDirectory).toHaveBeenCalledWith());
  });

  it("打开失败时展示 Tauri 返回的字符串错误", async () => {
    openDataDirectory.mockRejectedValue(
      "Not allowed to open path C:\\Users\\tester\\KnowRealm",
    );

    renderSection();

    fireEvent.click(
      await screen.findByRole("button", { name: "打开数据目录" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not allowed to open path C:\\Users\\tester\\KnowRealm",
    );
  });

  it("确认弹窗预告耗时、重启与任务恢复，并展示所选新位置", async () => {
    renderSection();
    await openConfirmDialog();

    expect(
      screen.getByText("数据量越大耗时越久，迁移期间请勿关闭应用。"),
    ).toBeInTheDocument();
    expect(screen.getByText("迁移完成后应用将自动重启。")).toBeInTheDocument();
    expect(
      screen.getByText(
        "进行中的 AI 任务会被中断，应用重启后自动恢复，无需手动处理。",
      ),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("D:\\KnowRealmNew")).toHaveAttribute(
      "readonly",
    );
    expect(changeDataDirectory).not.toHaveBeenCalled();
  });

  it("确认后调用迁移命令，生产构建自动重启应用", async () => {
    vi.stubEnv("DEV", false);
    changeDataDirectory.mockResolvedValue(undefined);
    relaunchApplication.mockResolvedValue(undefined);

    renderSection();
    const target = await openConfirmDialog();
    fireEvent.click(screen.getByRole("button", { name: "确认并迁移" }));

    await waitFor(() =>
      expect(changeDataDirectory).toHaveBeenCalledWith(target),
    );
    await waitFor(() => expect(relaunchApplication).toHaveBeenCalledWith());
    expect(
      await screen.findByText("迁移完成，正在重启应用…"),
    ).toBeInTheDocument();
  });

  it("开发构建不自动重启：弹窗不可关闭，唯一按钮退出应用", async () => {
    changeDataDirectory.mockResolvedValue(undefined);
    exitApplication.mockResolvedValue(undefined);

    renderSection();
    await openConfirmDialog();
    fireEvent.click(screen.getByRole("button", { name: "确认并迁移" }));

    expect(
      await screen.findByText(
        "迁移完成。当前为开发模式，已跳过自动重启——请停止 tauri dev 后重新启动应用，即可使用新数据目录。",
      ),
    ).toBeInTheDocument();
    expect(relaunchApplication).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "关闭" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出应用" }));
    await waitFor(() => expect(exitApplication).toHaveBeenCalledOnce());
  });

  it("迁移中展示进度事件百分比且无法重复确认", async () => {
    let emitProgress:
      | ((progress: { copiedBytes: number; totalBytes: number }) => void)
      | undefined;
    listenMigrationProgress.mockImplementation((handler) => {
      emitProgress = handler;
      return Promise.resolve(() => {});
    });
    changeDataDirectory.mockReturnValue(new Promise(() => {}));

    renderSection();
    await openConfirmDialog();
    fireEvent.click(screen.getByRole("button", { name: "确认并迁移" }));

    expect(await screen.findByText("正在迁移数据…")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "确认并迁移" }),
    ).not.toBeInTheDocument();

    act(() => emitProgress?.({ copiedBytes: 25, totalBytes: 100 }));

    expect(screen.getByText("正在迁移数据（25%）")).toBeInTheDocument();
    expect(changeDataDirectory).toHaveBeenCalledTimes(1);
  });

  it("非空目录拒绝映射为中文文案且不重启，可关闭弹窗", async () => {
    const alerts = await confirmAndFailWith("DATA_DIRECTORY_NOT_EMPTY");

    expect(alerts[0]).toHaveTextContent("所选目录不是空目录");
    expect(relaunchApplication).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "关闭" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("嵌套目录错误码映射为中文文案", async () => {
    const alerts = await confirmAndFailWith("DATA_DIRECTORY_NESTED");

    expect(alerts[0]).toHaveTextContent("位于当前数据目录内部");
    expect(relaunchApplication).not.toHaveBeenCalled();
  });

  it("迁移阶段失败展示摘要与 io 明细", async () => {
    const alerts = await confirmAndFailWith(
      "DATA_DIRECTORY_MIGRATION_FAILED: 拒绝访问。 (os error 5)",
    );

    expect(alerts[0]).toHaveTextContent("数据迁移失败，原数据未受影响");
    expect(alerts[0]).toHaveTextContent("os error 5");
    expect(relaunchApplication).not.toHaveBeenCalled();
  });
});
