import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

beforeEach(() => {
  invoke.mockReset();
  vi.resetModules();
});

describe("getSidecarConfig", () => {
  it("首次读取失败后允许下一次调用重新读取配置", async () => {
    invoke
      .mockRejectedValueOnce(new Error("sidecar 尚未启动"))
      .mockResolvedValueOnce({
        baseUrl: "http://127.0.0.1:43127",
        token: "launch-token",
      });
    const { getSidecarConfig } = await import("./sidecar");

    await expect(getSidecarConfig()).rejects.toThrow("sidecar 尚未启动");
    await expect(getSidecarConfig()).resolves.toEqual({
      baseUrl: "http://127.0.0.1:43127",
      token: "launch-token",
    });
    expect(invoke).toHaveBeenCalledTimes(2);
  });
});
