import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CloseBehaviorPreference } from "./preferences";

type CloseHandler = (event: {
  preventDefault: () => void;
}) => void | Promise<void>;

const runtime = vi.hoisted(() => ({
  closeHandler: undefined as CloseHandler | undefined,
  hide: vi.fn(),
  preventDefault: vi.fn(),
  onExitRequested: vi.fn(),
  getBehavior: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(() => true) }));

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    onCloseRequested: vi.fn(async (handler: CloseHandler) => {
      runtime.closeHandler = handler;
      return () => undefined;
    }),
    hide: runtime.hide,
  }),
}));

vi.mock("@tauri-apps/plugin-autostart", () => ({
  enable: vi.fn(async () => undefined),
  disable: vi.fn(async () => undefined),
}));

async function fireClose(behavior: CloseBehaviorPreference | null) {
  runtime.preventDefault.mockReset();
  runtime.getBehavior.mockReturnValue(behavior);
  expect(runtime.closeHandler).toBeTypeOf("function");
  await runtime.closeHandler?.({ preventDefault: runtime.preventDefault });
}

beforeEach(async () => {
  runtime.hide.mockReset().mockResolvedValue(undefined);
  runtime.onExitRequested.mockReset();
  runtime.getBehavior.mockReset();
  vi.clearAllMocks();
  const { mountCloseBehavior } = await import("./preferences");
  await mountCloseBehavior({
    getBehavior: () => runtime.getBehavior(),
    onExitRequested: runtime.onExitRequested,
  });
});

describe("关窗分流", () => {
  it("TRAY：先 preventClose 再隐藏主窗口，不走退出", async () => {
    await fireClose("TRAY");

    expect(runtime.preventDefault).toHaveBeenCalledOnce();
    expect(runtime.hide).toHaveBeenCalledOnce();
    expect(runtime.preventDefault.mock.invocationCallOrder[0]).toBeLessThan(
      runtime.hide.mock.invocationCallOrder[0],
    );
    expect(runtime.onExitRequested).not.toHaveBeenCalled();
  });

  it("EXIT：preventClose 后收敛到 safeExit，不隐藏窗口", async () => {
    await fireClose("EXIT");

    expect(runtime.preventDefault).toHaveBeenCalledOnce();
    expect(runtime.onExitRequested).toHaveBeenCalledOnce();
    expect(runtime.hide).not.toHaveBeenCalled();
  });

  it("偏好未载入（null）不拦截，走基座默认的直接退出", async () => {
    await fireClose(null);

    expect(runtime.preventDefault).not.toHaveBeenCalled();
    expect(runtime.hide).not.toHaveBeenCalled();
    expect(runtime.onExitRequested).not.toHaveBeenCalled();
  });

  it("策略切换即时生效：同一挂载先后按 TRAY、EXIT 分流", async () => {
    await fireClose("TRAY");
    await fireClose("EXIT");

    expect(runtime.hide).toHaveBeenCalledOnce();
    expect(runtime.onExitRequested).toHaveBeenCalledOnce();
  });
});

describe("开机自启", () => {
  it("true 调 enable、false 调 disable", async () => {
    const { setAutostart } = await import("./preferences");
    const { enable, disable } = await import("@tauri-apps/plugin-autostart");

    await setAutostart(true);
    expect(enable).toHaveBeenCalledOnce();
    expect(disable).not.toHaveBeenCalled();

    await setAutostart(false);
    expect(disable).toHaveBeenCalledOnce();
  });

  it("非桌面环境无操作", async () => {
    const { isTauri } = await import("@tauri-apps/api/core");
    vi.mocked(isTauri).mockReturnValueOnce(false);
    const { enable, disable } = await import("@tauri-apps/plugin-autostart");

    const { setAutostart } = await import("./preferences");
    await setAutostart(true);

    expect(enable).not.toHaveBeenCalled();
    expect(disable).not.toHaveBeenCalled();
  });
});
