// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

type TodaySummaryTodo = components["schemas"]["TodaySummaryTodoOut"];

const PENDING_URL = `${TEST_SIDECAR_URL}/api/today/pending-summaries`;

const todo: TodaySummaryTodo = {
  record_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  title: "新录音 1",
  course_id: "9fa85f64-5717-4562-b3fc-2c963f66afa6",
  course_name: "langchain学习",
  ready_at: "2026-09-09T08:00:00Z",
};

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

// 待确认总结渲染在行动流内，学习链复用同一真实查询。
function actionFlow(): HTMLElement {
  const heading = screen.getByText("行动流");
  const card = heading.closest("section");
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

describe("今日行动流待确认总结", () => {
  it("有条目时渲染在行动流内，含记录行与去确认链接", async () => {
    server.use(http.get(PENDING_URL, () => HttpResponse.json([todo])));

    render(<App />);

    await screen.findByText("行动流");
    const card = actionFlow();
    expect(
      await within(card).findByRole("heading", { name: "等待确认的总结" }),
    ).toBeInTheDocument();
    const list = within(card).getByRole("list", { name: "待确认总结列表" });
    const link = within(list).getByRole("link", { name: /新录音 1/ });
    expect(link).toHaveAttribute("href", `/records/${todo.record_id}`);
    expect(link).toHaveTextContent("langchain学习");
    expect(link).toHaveTextContent("去确认");
  });

  it("无待确认总结时不渲染区块", async () => {
    render(<App />);

    await screen.findByRole("heading", { name: "学习趋势" });
    expect(
      screen.queryByRole("heading", { name: "等待确认的总结" }),
    ).not.toBeInTheDocument();
  });

  it("读取失败显示行内错误与重试", async () => {
    let fail = true;
    server.use(
      http.get(PENDING_URL, () =>
        fail
          ? HttpResponse.json({ detail: "sidecar 抖动" }, { status: 500 })
          : HttpResponse.json([todo]),
      ),
    );

    render(<App />);

    const alert = await screen.findByRole("alert", undefined, {
      timeout: 8_000,
    });
    expect(alert).toHaveTextContent("今日待办暂时无法读取");

    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("heading", { name: "等待确认的总结" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }, 20_000);
});
