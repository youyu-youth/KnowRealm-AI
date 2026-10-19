// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { BaseChart } from "@/charts/BaseChart";
import { ProfileActivityHeatmap } from "@/features/learning-profile/ProfileActivityHeatmap";
import type { TodayTrendPoint } from "@/features/today/api/today";
import "@/i18n";

vi.mock("@/charts/BaseChart", () => ({
  BaseChart: vi.fn(({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel} />
  )),
}));

describe("学习活动热力图", () => {
  it("按真实日期排列，保留零值而不补造缺失日期，点击回传对应日期", () => {
    const onSelect = vi.fn();
    const points = [
      { date: "2026-10-19", total_ms: 3600000 },
      { date: "2026-10-17", total_ms: 0 },
    ] satisfies TodayTrendPoint[];
    render(
      <ProfileActivityHeatmap
        points={points}
        selected="2026-10-17"
        onSelect={onSelect}
      />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(/周一至周日/);
    const props = vi.mocked(BaseChart).mock.lastCall?.[0];
    expect(props?.option.calendar).toMatchObject({
      range: ["2026-10-17", "2026-10-19"],
      orient: "vertical",
      dayLabel: { firstDay: 1 },
    });
    expect(props?.option.series).toMatchObject([
      {
        data: [
          { value: ["2026-10-17", 0] },
          { value: ["2026-10-19", 3600000] },
        ],
      },
    ]);
    const event: Parameters<
      NonNullable<ComponentProps<typeof BaseChart>["onItemSelect"]>
    >[0] = {
      type: "click",
      componentType: "series",
      componentSubType: "heatmap",
      componentIndex: 0,
      name: "2026-10-19",
      dataIndex: 1,
      data: ["2026-10-19", 3600000],
      value: ["2026-10-19", 3600000],
      $vars: [],
    };
    props?.onItemSelect?.(event);
    expect(onSelect).toHaveBeenCalledWith("2026-10-19");
    props?.onItemSelect?.({ ...event, componentType: "calendar" });
    props?.onItemSelect?.({ ...event, dataIndex: 9 });
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("空统计展示空态，不生成零值热力图", () => {
    render(
      <ProfileActivityHeatmap
        points={[]}
        selected="2026-10-19"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("暂无学习活动统计")).toBeVisible();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
