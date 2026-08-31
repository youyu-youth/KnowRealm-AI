// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

const runtime = vi.hoisted(() => ({
  onboarded: false,
  isOnboardingRequired: vi.fn(),
  completeOnboarding: vi.fn(),
  getDataDirectory: vi.fn(),
  chooseDataDirectory: vi.fn(),
  chooseImportArchive: vi.fn(),
  importFromArchive: vi.fn(),
  changeDataDirectory: vi.fn(),
  listenMigrationProgress: vi.fn(),
}));

vi.mock("@/services/tauri/onboarding", () => ({
  isOnboardingRequired: runtime.isOnboardingRequired,
  completeOnboarding: runtime.completeOnboarding,
}));

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/services/tauri/dataDirectory", () => ({
  getDataDirectory: runtime.getDataDirectory,
  openDataDirectory: vi.fn(),
  changeDataDirectory: runtime.changeDataDirectory,
  chooseDataDirectory: runtime.chooseDataDirectory,
  chooseImportArchive: runtime.chooseImportArchive,
  importFromArchive: runtime.importFromArchive,
  listenMigrationProgress: runtime.listenMigrationProgress,
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  runtime.onboarded = false;
  runtime.isOnboardingRequired.mockImplementation(async () => {
    return !runtime.onboarded;
  });
  runtime.completeOnboarding.mockImplementation(async () => {
    runtime.onboarded = true;
  });
  runtime.getDataDirectory
    .mockReset()
    .mockResolvedValue("C:\\Users\\tester\\KnowRealm");
  runtime.chooseDataDirectory.mockReset();
  runtime.chooseImportArchive.mockReset();
  runtime.importFromArchive.mockReset();
  runtime.changeDataDirectory.mockReset();
  runtime.listenMigrationProgress.mockReset().mockResolvedValue(() => {});
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function usePreferenceWriteSpy() {
  let writes = 0;
  server.use(
    http.put(`${TEST_SIDECAR_URL}/api/settings/preferences`, () => {
      writes += 1;
      return HttpResponse.json({});
    }),
  );
  return () => writes;
}

// StepHeader 不依赖目录查询，先等路径就绪再交互。
async function gotoDirectoryStep() {
  await screen.findByRole("heading", { name: "选择数据存放位置" });
  await screen.findByDisplayValue("C:\\Users\\tester\\KnowRealm");
}

describe("首启三步向导", () => {
  it("非首启直接进今日，直达 /onboarding 也被弹回", async () => {
    runtime.onboarded = true;
    window.history.replaceState(null, "", "/onboarding");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "今日" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("选择数据存放位置")).not.toBeInTheDocument();
  });

  it("首启从任意地址分流进向导，且没有 AppShell 导航可绕过", async () => {
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "选择数据存放位置" }),
    ).toBeInTheDocument();
    expect(screen.getByText("第 1 步，共 3 步")).toBeInTheDocument();
    expect(
      await screen.findByDisplayValue("C:\\Users\\tester\\KnowRealm"),
    ).toHaveAttribute("readonly");
    expect(
      screen.queryByRole("link", { name: "收件箱" }),
    ).not.toBeInTheDocument();
  });

  it("数据目录位于 OneDrive 时展示黄字警告但不阻断", async () => {
    runtime.getDataDirectory.mockResolvedValue(
      "C:\\Users\\tester\\OneDrive\\KnowRealm",
    );

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "OneDrive 同步范围",
    );
    expect(
      screen.getByRole("button", { name: "使用默认目录开始" }),
    ).toBeEnabled();
  });

  it("三步全部跳过：完成页写 onboarded 后进首页，向导全程不写 last_route", async () => {
    const preferenceWrites = usePreferenceWriteSpy();

    render(<App />);
    await gotoDirectoryStep();
    fireEvent.click(screen.getByRole("button", { name: "使用默认目录开始" }));

    expect(
      await screen.findByRole("heading", { name: "配置 AI 服务" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "稍后在设置中配置" }));

    expect(
      await screen.findByRole("heading", { name: "认识一下（可选）" }),
    ).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "跳过" }));

    expect(
      await screen.findByRole("heading", { name: "一切就绪" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("所有设置可稍后在设置页修改。"),
    ).toBeInTheDocument();
    expect(preferenceWrites()).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "进入 KnowRealm" }));

    expect(
      await screen.findByRole("heading", { name: "今日" }),
    ).toBeInTheDocument();
    expect(runtime.completeOnboarding).toHaveBeenCalledOnce();
    expect(runtime.completeOnboarding).toHaveBeenCalledWith();
  });

  it("③保存建档发出完整档案，跳过则不发任何档案请求", async () => {
    const savedProfiles: unknown[] = [];
    server.use(
      http.put(`${TEST_SIDECAR_URL}/api/profile`, async ({ request }) => {
        savedProfiles.push(await request.json());
        return HttpResponse.json({
          nickname: null,
          primary_role: "STUDENT",
          about_me: "三年后端，正在补操作系统基础。",
        });
      }),
    );

    render(<App />);
    await gotoDirectoryStep();
    fireEvent.click(screen.getByRole("button", { name: "使用默认目录开始" }));
    await screen.findByRole("heading", { name: "配置 AI 服务" });
    fireEvent.click(screen.getByRole("button", { name: "稍后在设置中配置" }));
    await screen.findByRole("heading", { name: "认识一下（可选）" });

    fireEvent.click(await screen.findByRole("radio", { name: "学生" }));
    fireEvent.change(screen.getByLabelText("自我介绍"), {
      target: { value: "三年后端，正在补操作系统基础。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并继续" }));

    expect(
      await screen.findByRole("heading", { name: "一切就绪" }),
    ).toBeInTheDocument();
    expect(savedProfiles).toEqual([
      {
        primary_role: "STUDENT",
        nickname: null,
        about_me: "三年后端，正在补操作系统基础。",
      },
    ]);
  });

  it("导入失败在向导内报错，可关闭后重新选择导出包重试", async () => {
    render(<App />);
    await gotoDirectoryStep();

    runtime.chooseImportArchive.mockResolvedValue("D:\\backup.zip");
    runtime.importFromArchive.mockRejectedValueOnce(
      "导出包不存在：D:\\backup.zip",
    );
    fireEvent.click(screen.getByRole("button", { name: "从导出包导入" }));
    fireEvent.click(await screen.findByRole("button", { name: "导入并重启" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "导出包不存在：D:\\backup.zip",
    );
    expect(
      screen.getByText("导入未执行，应用仍在运行，可重新选择导出包重试。"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "从导出包导入" }),
    );

    await waitFor(() =>
      expect(runtime.chooseImportArchive).toHaveBeenCalledTimes(2),
    );
    expect(runtime.importFromArchive).toHaveBeenCalledOnce();
  });

  it("导入就绪后停在等待重启（开发模式），不自动 relaunch", async () => {
    render(<App />);
    await gotoDirectoryStep();

    runtime.chooseImportArchive.mockResolvedValue("D:\\backup.zip");
    runtime.importFromArchive.mockResolvedValue(undefined);
    fireEvent.click(screen.getByRole("button", { name: "从导出包导入" }));
    fireEvent.click(await screen.findByRole("button", { name: "导入并重启" }));

    expect(
      await screen.findByRole("button", { name: "退出应用" }),
    ).toBeInTheDocument();
    expect(runtime.importFromArchive).toHaveBeenCalledWith("D:\\backup.zip");
    expect(runtime.importFromArchive).toHaveBeenCalledOnce();
  });

  it("更改位置复用迁移链：目标非空时在弹窗内报错且不停应用", async () => {
    render(<App />);
    await gotoDirectoryStep();

    runtime.chooseDataDirectory.mockResolvedValue("D:\\KnowRealmNew");
    runtime.changeDataDirectory.mockRejectedValueOnce(
      "DATA_DIRECTORY_NOT_EMPTY: 所选目录不是空目录",
    );
    fireEvent.click(screen.getByRole("button", { name: "更改位置" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认并迁移" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "所选目录不是空目录",
    );
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));

    expect(
      await screen.findByRole("button", { name: "使用默认目录开始" }),
    ).toBeEnabled();
  });

  it("更改位置选择 OneDrive 目录时在确认弹窗内就地警示", async () => {
    render(<App />);
    await gotoDirectoryStep();

    runtime.chooseDataDirectory.mockResolvedValue(
      "C:\\Users\\tester\\OneDrive - Contoso\\KnowRealmNew",
    );
    fireEvent.click(screen.getByRole("button", { name: "更改位置" }));

    expect(await screen.findByText(/OneDrive 同步范围内/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认并迁移" })).toBeEnabled();
  });
});
