// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { LlmUsageCard } from "./LlmUsageCard";

const { getLlmUsage } = vi.hoisted(() => ({
  getLlmUsage: vi.fn(),
}));

vi.mock("@/features/settings/api/settings", () => ({
  settingsApi: { getLlmUsage },
}));

function dailyPoint(date: string, totalTokens: number, callCount: number) {
  return { date, total_tokens: totalTokens, call_count: callCount };
}

describe("LlmUsageCard", () => {
  beforeEach(() => {
    getLlmUsage.mockReset();
  });

  it("展示按模型汇总的用量表与趋势图", async () => {
    getLlmUsage.mockResolvedValue({
      items: [
        {
          model: "qwen-plus",
          call_count: 1234,
          input_tokens: 90000,
          output_tokens: 33445,
          total_tokens: 12345,
          error_count: 2,
        },
      ],
      daily: [
        dailyPoint("2026-08-09", 12345, 12),
        ...Array.from({ length: 29 }, (_, index) =>
          dailyPoint(`2026-08-${String(10 + index).padStart(2, "0")}`, 0, 0),
        ),
      ],
    });

    renderWithQuery(<LlmUsageCard />);

    expect(await screen.findByText("qwen-plus")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("90,000")).toBeInTheDocument();
    expect(screen.getByText("33,445")).toBeInTheDocument();
    expect(screen.getByText("12,345")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "近 30 天每日 token 用量趋势图" }),
    ).toBeInTheDocument();
  });

  it("近 30 天无调用时展示空态且不渲染表格", async () => {
    getLlmUsage.mockResolvedValue({
      items: [],
      daily: Array.from({ length: 30 }, (_, index) =>
        dailyPoint(`2026-08-${String(1 + index).padStart(2, "0")}`, 0, 0),
      ),
    });

    renderWithQuery(<LlmUsageCard />);

    expect(await screen.findByText("近 30 天暂无 AI 调用")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: "近 30 天每日 token 用量趋势图" }),
    ).not.toBeInTheDocument();
  });

  it("读取失败时展示错误与重试", async () => {
    getLlmUsage.mockRejectedValue(new Error("后端不可用"));

    renderWithQuery(<LlmUsageCard />);

    expect(await screen.findByText("后端不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });
});
