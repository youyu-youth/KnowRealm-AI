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

    await waitFor(() =>
      expect(openDataDirectory).toHaveBeenCalledWith(
        "C:\\Users\\tester\\KnowRealm",
      ),
    );
  });
});
