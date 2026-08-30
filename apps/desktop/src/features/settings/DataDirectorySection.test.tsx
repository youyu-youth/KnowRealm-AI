// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { DataDirectorySection } from "./DataDirectorySection";

const { getDataDirectory, openDataDirectory } = vi.hoisted(() => ({
  getDataDirectory: vi.fn(),
  openDataDirectory: vi.fn(),
}));

vi.mock("@/services/tauri/dataDirectory", () => ({
  getDataDirectory,
  openDataDirectory,
}));

describe("DataDirectorySection", () => {
  beforeEach(() => {
    getDataDirectory.mockReset();
    openDataDirectory.mockReset();
  });

  it("展示当前数据目录并通过系统资源管理器打开", async () => {
    getDataDirectory.mockResolvedValue("C:\\Users\\tester\\KnowRealm");
    openDataDirectory.mockResolvedValue(undefined);

    renderWithQuery(<DataDirectorySection />);

    expect(
      await screen.findByDisplayValue("C:\\Users\\tester\\KnowRealm"),
    ).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "打开数据目录" }));

    await waitFor(() => expect(openDataDirectory).toHaveBeenCalledWith());
  });

  it("打开失败时展示 Tauri 返回的字符串错误", async () => {
    getDataDirectory.mockResolvedValue("C:\\Users\\tester\\KnowRealm");
    openDataDirectory.mockRejectedValue(
      "Not allowed to open path C:\\Users\\tester\\KnowRealm",
    );

    renderWithQuery(<DataDirectorySection />);

    fireEvent.click(
      await screen.findByRole("button", { name: "打开数据目录" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not allowed to open path C:\\Users\\tester\\KnowRealm",
    );
  });
});
