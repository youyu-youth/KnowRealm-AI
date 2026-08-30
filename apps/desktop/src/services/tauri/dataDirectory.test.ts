import { beforeEach, describe, expect, it, vi } from "vitest";
import { getDataDirectory, openDataDirectory } from "./dataDirectory";

const { invoke } = vi.hoisted(() => ({
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke }));

describe("dataDirectory", () => {
  beforeEach(() => {
    invoke.mockReset();
  });

  it("通过 Tauri command 读取并用 opener 打开数据目录", async () => {
    invoke.mockResolvedValue("C:\\Users\\tester\\KnowRealm");

    await expect(getDataDirectory()).resolves.toBe(
      "C:\\Users\\tester\\KnowRealm",
    );
    await openDataDirectory();

    expect(invoke).toHaveBeenCalledWith("get_data_directory");
    expect(invoke).toHaveBeenCalledWith("open_data_directory");
  });
});
