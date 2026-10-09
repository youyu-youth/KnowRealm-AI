// @vitest-environment jsdom
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { TodayFocus } from "@/features/today/components/TodayFocus";

afterEach(() => vi.useRealTimers());

describe("今日专注示意计时", () => {
  it("按墙钟计时，暂停不消耗时间，继续和结束可用", () => {
    vi.useFakeTimers();
    renderWithQuery(<TodayFocus />);
    expect(screen.getByRole("timer")).toHaveTextContent("25:00");
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    act(() => vi.advanceTimersByTime(3_000));
    expect(screen.getByRole("timer")).toHaveTextContent("24:57");
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByRole("timer")).toHaveTextContent("24:57");
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByRole("timer")).toHaveTextContent("24:55");
    fireEvent.click(screen.getByRole("button", { name: "结束" }));
    expect(screen.getByRole("timer")).toHaveTextContent("00:00");
    expect(screen.getByRole("button", { name: "结束" })).toBeDisabled();
    expect(screen.getByText(/不计入学习统计/)).toBeInTheDocument();
  });

  it("休眠后的下一次 tick 按当前时间收口，而非按 tick 次数累计", () => {
    vi.useFakeTimers();
    renderWithQuery(<TodayFocus />);
    fireEvent.click(screen.getByRole("button", { name: "开始" }));
    act(() => {
      vi.setSystemTime(Date.now() + 30 * 60_000);
      vi.advanceTimersByTime(250);
    });
    expect(screen.getByRole("timer")).toHaveTextContent("00:00");
    expect(screen.getByRole("button", { name: "开始" })).toBeEnabled();
  });

  it("编辑时长校验范围并重置准备状态", async () => {
    renderWithQuery(<TodayFocus />);
    fireEvent.click(screen.getByRole("button", { name: "编辑时长" }));
    const input = await screen.findByRole("spinbutton", {
      name: "专注时长（分钟）",
    });
    fireEvent.change(input, { target: { value: "0" } });
    expect(screen.getByRole("button", { name: "保存时长" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "保存时长" }));
    expect(screen.getByRole("timer")).toHaveTextContent("60:00");
  });
});
