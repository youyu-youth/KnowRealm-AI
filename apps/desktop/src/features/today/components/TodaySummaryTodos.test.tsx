// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

describe("今日页待确认总结条带", () => {
  it("有条目时渲染标题、记录行与去确认链接", async () => {
    server.use(http.get(PENDING_URL, () => HttpResponse.json([todo])));

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "等待确认的总结" }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "待确认总结列表" });
    expect(list).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /新录音 1/ });
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

  it("读取失败显示可重试的错误区", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("heading", { name: "等待确认的总结" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }, 20_000);
});
