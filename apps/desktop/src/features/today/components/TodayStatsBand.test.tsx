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

// 与后端一致：按捕获日补零的连续序列。
function trendResponse(
  days: number,
  msByOffset: Record<number, number> = {},
): TodayTrendPoint[] {
  const today = new Date();
  return Array.from({ length: days }, (_, index) => {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - (days - 1 - index));
    return {
      date: day.toISOString().slice(0, 10),
      total_ms: msByOffset[index] ?? 0,
    };
  });
}

// 数值把单位拆在小号 span 里（textContent 连续，但不是单一文本节点），
// 因此按标签定位相邻的数值容器断言完整文本；作用域锁统计带分节，
// 避免与侧栏「知识空间」等导航文案及图表 SVG 数字碰撞。
function statsSection(): HTMLElement {
  const heading = screen.getByRole("heading", { name: "学习趋势" });
  const section = heading.closest("section");
  expect(section).not.toBeNull();
  return section as HTMLElement;
}

async function cellValueText(label: string): Promise<string> {
  return waitFor(
    () => {
      const value =
        within(statsSection()).getByText(label).nextElementSibling?.textContent;
      expect(value).toBeTruthy();
      return value ?? "";
    },
    { timeout: 2_000 },
  );
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
  it("渲染六格指标带与趋势图，习题格显示已作答/生成双数", async () => {
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(fullStats)),
      http.get(TREND_URL, () =>
        HttpResponse.json(trendResponse(7, { 3: 5_400_000 })),
      ),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "学习趋势" }),
    ).toBeInTheDocument();
    expect(await cellValueText("累计学习时长")).toBe("1 小时 30 分");
    expect(await cellValueText("学习记录")).toBe("42");
    expect(await cellValueText("知识空间")).toBe("5");
    expect(await cellValueText("AI 总结次数")).toBe("30");
    expect(await cellValueText("习题（已作答 / 生成）")).toBe("80 / 120");
    expect(await cellValueText("问答轮次")).toBe("200");
    expect(screen.getByRole("img", { name: "学习趋势图" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "近 7 天" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("不足一小时的时长按分钟呈现", async () => {
    server.use(
      http.get(STATS_URL, () =>
        HttpResponse.json({ ...zeroStats, total_learning_ms: 5 * 60_000 }),
      ),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(7))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("5 分钟");
  });

  it("整小时省略分钟", async () => {
    server.use(
      http.get(STATS_URL, () =>
        HttpResponse.json({ ...zeroStats, total_learning_ms: 7_200_000 }),
      ),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(7))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("2 小时");
  });

  it("近 7 / 30 天切换即按对应 days 重取趋势", async () => {
    const trendUrls: URL[] = [];
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(fullStats)),
      http.get(TREND_URL, ({ request }) => {
        trendUrls.push(new URL(request.url));
        return HttpResponse.json(trendResponse(7, { 3: 5_400_000 }));
      }),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("1 小时 30 分");
    expect(trendUrls[0]?.searchParams.get("days")).toBe("7");

    fireEvent.click(screen.getByRole("tab", { name: "近 30 天" }));

    await waitFor(() =>
      expect(
        trendUrls.some((url) => url.searchParams.get("days") === "30"),
      ).toBe(true),
    );
    expect(screen.getByRole("tab", { name: "近 30 天" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.click(screen.getByRole("tab", { name: "近 7 天" }));

    await waitFor(() =>
      expect(
        trendUrls.filter((url) => url.searchParams.get("days") === "7"),
      ).toHaveLength(2),
    );
    expect(screen.getByRole("tab", { name: "近 7 天" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("统计加载不阻塞待办区", async () => {
    server.use(
      http.get(STATS_URL, async () => {
        await delay(200);
        return HttpResponse.json(zeroStats);
      }),
      http.get(TREND_URL, async () => {
        await delay(200);
        return HttpResponse.json(trendResponse(7));
      }),
    );

    render(<App />);

    const loading = await screen.findByRole("status");
    expect(loading).toHaveTextContent("正在读取学习统计");
    expect(screen.getByText("今天没有待处理事项")).toBeInTheDocument();

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
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(7))),
    );

    render(<App />);

    const alert = await screen.findByRole("alert", undefined, {
      timeout: 8_000,
    });
    expect(alert).toHaveTextContent("学习统计暂时无法读取");
    expect(alert).toHaveTextContent("本地服务可能仍在启动，请稍后重试。");

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(await cellValueText("累计学习时长")).toBe("0 分钟");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }, 20_000);

  it("空库显示全 0 与图表容器", async () => {
    server.use(
      http.get(STATS_URL, () => HttpResponse.json(zeroStats)),
      http.get(TREND_URL, () => HttpResponse.json(trendResponse(7))),
    );

    render(<App />);

    expect(await cellValueText("累计学习时长")).toBe("0 分钟");
    expect(await cellValueText("学习记录")).toBe("0");
    expect(await cellValueText("知识空间")).toBe("0");
    expect(await cellValueText("AI 总结次数")).toBe("0");
    expect(await cellValueText("习题（已作答 / 生成）")).toBe("0 / 0");
    expect(await cellValueText("问答轮次")).toBe("0");
    expect(screen.getByRole("img", { name: "学习趋势图" })).toBeInTheDocument();
  });
});
