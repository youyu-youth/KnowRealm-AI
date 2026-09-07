// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

type TodayStats = components["schemas"]["TodayStatsOut"];
type TodayTrendPoint = components["schemas"]["TodayTrendPointOut"];

const STATS_URL = `${TEST_SIDECAR_URL}/api/today/stats`;
const TREND_URL = `${TEST_SIDECAR_URL}/api/today/stats/trend`;

const fullStats: TodayStats = {
  total_learning_ms: 5_400_000,
  record_count: 42,
  course_count: 5,
  ai_summary_count: 30,
  quiz_generated_count: 120,
  quiz_answered_count: 80,
  chat_turn_count: 200,
};

const zeroStats: TodayStats = {
  total_learning_ms: 0,
  record_count: 0,
  course_count: 0,
  ai_summary_count: 0,
  quiz_generated_count: 0,
  quiz_answered_count: 0,
  chat_turn_count: 0,
};

// 与后端一致：按捕获日补零的连续序列。index = 距最早一天的天序号：
// 26 → 3 天前（近 7 天内），19 → 10 天前（前一周期内）。
function trendResponse(
  days: number,
  msByIndex: Record<number, number> = {},
): TodayTrendPoint[] {
  const today = new Date();
  return Array.from({ length: days }, (_, index) => {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - (days - 1 - index));
    return {
      date: day.toISOString().slice(0, 10),
      total_ms: msByIndex[index] ?? 0,
    };
  });
}

const fullTrend = trendResponse(30, { 26: 5_400_000, 19: 3_600_000 });

// 统计带主卡为 region（aria-label=学习趋势），数值把单位拆在小号 span 里
// （textContent 连续但非单一文本节点），故按标签定位相邻容器断言完整文本，
// 同时与侧栏导航文案、图表 SVG 内的数字隔离。
function statsRegion(): HTMLElement {
  return screen.getByRole("region", { name: "学习趋势" });
}

function insightRegion(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

async function cellValueText(label: string): Promise<string> {
  return waitFor(
    () => {
      const value =
        within(statsRegion()).getByText(label).nextElementSibling?.textContent;
      expect(value).toBeTruthy();
      return value ?? "";
    },
    { timeout: 2_000 },
  );
}

// 大数字形如「1.5 h」（数值 + 小号单位 span），用 P 元素整文本匹配。
function expectBigNumber(text: string) {
  expect(
    within(statsRegion()).getByText(
      (_content, element) =>
        element?.tagName === "P" && element.textContent === text,
    ),
  ).toBeInTheDocument();
}

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/services/tauri/recording", () => ({
  setRecordingKeepAwake: vi.fn().mockResolvedValue(undefined),
  hideWindowTemporarily: vi.fn().mockResolvedValue(undefined),
}));

vi.stubGlobal("scrollTo", vi.fn());

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("今日页统计带", () => {
  it("趋势主卡渲染大数字、较上周对比、六格指标与趋势图", async () => {
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(fullStats)),
      http.get(TREND_URL, () => HttpResponse.json(fullTrend)),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "学习趋势" }),
    ).toBeInTheDocument();
    // 近 7 天窗口：总时长 1.5h，前一周期 1h → ↑ 50%。
    await waitFor(() => expectBigNumber("1.5 h"));
    expect(statsRegion().textContent).toContain("较上周");
    expect(statsRegion().textContent).toContain("↑ 50%");
    expect(await cellValueText("累计学习时长")).toBe("1 小时 30 分");
    expect(await cellValueText("学习记录")).toBe("42");
    expect(await cellValueText("知识空间")).toBe("5");
    expect(await cellValueText("AI 总结次数")).toBe("30");
    expect(await cellValueText("习题（已作答 / 生成）")).toBe("80 / 120");
    expect(await cellValueText("问答轮次")).toBe("200");
    expect(
      within(statsRegion()).getByRole("img", { name: "学习趋势图" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "近 7 天" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("洞察小图卡（示意数据）渲染四张卡与图例，不依赖统计查询", async () => {
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(fullStats)),
      http.get(TREND_URL, () => HttpResponse.json(fullTrend)),
    );

    render(<App />);

    expect(
      await screen.findByRole("region", { name: "学科能力雷达图" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "学习时间分布" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "学习专注度" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "学习进步趋势" }),
    ).toBeInTheDocument();
    expect(screen.getByText("今日焦点")).toBeInTheDocument();
    expect(screen.getByText("AI 助手")).toBeInTheDocument();
    expect(screen.getByText("学习成就")).toBeInTheDocument();

    expect(
      within(insightRegion("学科能力雷达图")).getByText("本周"),
    ).toBeInTheDocument();
    expect(
      within(insightRegion("学科能力雷达图")).getByText("上周"),
    ).toBeInTheDocument();
    expect(
      within(insightRegion("学科能力雷达图")).getAllByText("高等数学").length,
    ).toBeGreaterThan(0);
    expect(
      within(insightRegion("学习时间分布")).getByText("36%"),
    ).toBeInTheDocument();
    expect(
      within(insightRegion("学习时间分布")).getByText("28.6"),
    ).toBeInTheDocument();
    expect(
      within(insightRegion("学习进步趋势")).getByText("知识点掌握量"),
    ).toBeInTheDocument();
    for (const name of [
      "学科能力雷达图",
      "学习时间分布",
      "学习专注度",
      "学习进步趋势",
    ]) {
      expect(within(insightRegion(name)).getAllByText("示意").length).toBe(1);
    }
  });

  it("不足一小时的时长按分钟呈现", async () => {
    server.use(
      http.get(STATS_URL, () =>
        HttpResponse.json({ ...zeroStats, total_learning_ms: 5 * 60_000 }),
      ),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(30))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("5 分钟");
  });

  it("整小时省略分钟", async () => {
    server.use(
      http.get(STATS_URL, () =>
        HttpResponse.json({ ...zeroStats, total_learning_ms: 7_200_000 }),
      ),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(30))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("2 小时");
  });

  it("趋势固定请求 days=30，7/30 档切换为前端切片不发新请求", async () => {
    const trendUrls: URL[] = [];
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(fullStats)),
      http.get(TREND_URL, ({ request }) => {
        trendUrls.push(new URL(request.url));
        return HttpResponse.json(fullTrend);
      }),
    );

    render(<App />);

    await waitFor(() => expectBigNumber("1.5 h"));
    expect(trendUrls).toHaveLength(1);
    expect(trendUrls[0]?.searchParams.get("days")).toBe("30");

    fireEvent.click(screen.getByRole("tab", { name: "近 30 天" }));

    expectBigNumber("2.5 h");
    expect(screen.getByRole("tab", { name: "近 30 天" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(trendUrls).toHaveLength(1);

    fireEvent.click(screen.getByRole("tab", { name: "近 7 天" }));

    expectBigNumber("1.5 h");
    expect(trendUrls).toHaveLength(1);
  });

  it("统计加载不阻塞待办区，洞察卡照常渲染", async () => {
    server.use(
      http.get(STATS_URL, async () => {
        await delay(200);
        return HttpResponse.json(zeroStats);
      }),
      http.get(TREND_URL, async () => {
        await delay(200);
        return HttpResponse.json(trendResponse(30));
      }),
    );

    render(<App />);

    expect(await screen.findByText("正在读取学习统计")).toBeInTheDocument();
    expect(screen.queryByText("今天没有待处理事项")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "学习专注度" }),
    ).toBeInTheDocument();

    expect(await cellValueText("累计学习时长")).toBe("0 分钟");
  });

  it("统计失败时显示可重试的错误区", async () => {
    let fail = true;
    server.use(
      http.get(STATS_URL, () =>
        fail
          ? HttpResponse.json({ detail: "sidecar 抖动" }, { status: 500 })
          : HttpResponse.json(zeroStats),
      ),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(30))),
    );

    render(<App />);

    const alert = await screen.findByRole("alert", undefined, {
      timeout: 8_000,
    });
    expect(alert).toHaveTextContent("学习统计暂时无法读取");
    expect(alert).toHaveTextContent("本地服务可能仍在启动，请稍后重试。");

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    await waitFor(() => expectBigNumber("0.0 h"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }, 20_000);

  it("空库显示全 0、平线与示意卡，且无较上周对比", async () => {
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(zeroStats)),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(30))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("0 分钟");
    expect(await cellValueText("学习记录")).toBe("0");
    expect(await cellValueText("知识空间")).toBe("0");
    expect(await cellValueText("AI 总结次数")).toBe("0");
    expect(await cellValueText("习题（已作答 / 生成）")).toBe("0 / 0");
    expect(await cellValueText("问答轮次")).toBe("0");
    expectBigNumber("0.0 h");
    expect(within(statsRegion()).queryByText("较上周")).not.toBeInTheDocument();
    expect(
      within(statsRegion()).getByRole("img", { name: "学习趋势图" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "学习进步趋势" }),
    ).toBeInTheDocument();
  });
});
