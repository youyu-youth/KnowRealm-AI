const runtime = vi.hoisted(() => ({
  invoke: vi.fn(),
  isTauri: vi.fn(() => true),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: runtime.invoke,
  isTauri: runtime.isTauri,
}));

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  completeOnboarding,
  isOnboardingRequired,
  resetOnboardingCacheForTests,
} from "./onboarding";

describe("首启判定服务", () => {
  beforeEach(() => {
    runtime.invoke.mockReset();
    runtime.isTauri.mockReset().mockReturnValue(true);
    resetOnboardingCacheForTests();
  });

  it("非桌面环境不询问壳，直接判定无需向导", async () => {
    runtime.isTauri.mockReturnValue(false);

    await expect(isOnboardingRequired()).resolves.toBe(false);

    expect(runtime.invoke).not.toHaveBeenCalled();
  });

  it("首读透传壳结果，之后导航复用缓存不再发起 IPC", async () => {
    runtime.invoke.mockResolvedValue(false);

    await expect(isOnboardingRequired()).resolves.toBe(true);
    await expect(isOnboardingRequired()).resolves.toBe(true);

    expect(runtime.invoke).toHaveBeenCalledOnce();
    expect(runtime.invoke).toHaveBeenCalledWith("get_onboarding_state");
  });

  it("完成首启后本地翻转为无需向导，不等待壳二次读取", async () => {
    runtime.invoke.mockImplementation((command: string) => {
      expect(command).toBe("complete_onboarding");
      return Promise.resolve();
    });

    await completeOnboarding();

    await expect(isOnboardingRequired()).resolves.toBe(false);
    expect(runtime.invoke).toHaveBeenCalledOnce();
  });

  it("壳读取失败不落缓存，下次导航重新询问", async () => {
    runtime.invoke.mockRejectedValueOnce("desktop.json 不可读");

    await expect(isOnboardingRequired()).rejects.toBe("desktop.json 不可读");
    runtime.invoke.mockResolvedValue(true);

    await expect(isOnboardingRequired()).resolves.toBe(false);
    expect(runtime.invoke).toHaveBeenCalledTimes(2);
  });
});
