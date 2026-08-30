import { beforeEach, describe, expect, it, vi } from "vitest";
import { getDataDirectory, openDataDirectory } from "./dataDirectory";

const { invoke, openPath } = vi.hoisted(() => ({
  invoke: vi.fn(),
  openPath: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/plugin-opener", () => ({ openPath }));

describe("dataDirectory", () => {
  beforeEach(() => {
    invoke.mockReset();
    openPath.mockReset();
  });

  it("通过 Tauri command 读取并用 opener 打开数据目录", async () => {
    invoke.mockResolvedValue("C:\\Users\\tester\\KnowRealm");
    openPath.mockResolvedValue(undefined);

    await expect(getDataDirectory()).resolves.toBe(
      "C:\\Users\\tester\\KnowRealm",
    );
    await openDataDirectory("C:\\Users\\tester\\KnowRealm");

    expect(invoke).toHaveBeenCalledWith("get_data_directory");
    expect(openPath).toHaveBeenCalledWith("C:\\Users\\tester\\KnowRealm");
  });
});
