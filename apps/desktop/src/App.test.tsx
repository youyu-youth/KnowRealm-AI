// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("工作台骨架", () => {
  it("从今日导航到知识空间，并诚实禁用未接入入口", async () => {
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "今日" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /收件箱/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /开始录音/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("link", { name: "知识空间" }));

    expect(
      await screen.findByRole("heading", { name: "知识空间" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建知识空间" })).toBeEnabled();
  });

  it("未知地址提供返回今日的路径", async () => {
    window.history.replaceState(null, "", "/missing");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "页面不存在" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回今日" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("从受校验 URL 恢复课程搜索与筛选条件", async () => {
    let requestedUrl: URL | undefined;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        requestedUrl = new URL(request.url);
        return HttpResponse.json([]);
      }),
    );
    window.history.replaceState(
      null,
      "",
      "/spaces?q=%E6%93%8D%E4%BD%9C&education_stage=UNDERGRADUATE&course_type=MAJOR",
    );

    render(<App />);

    expect(
      await screen.findByRole("searchbox", { name: "搜索课程" }),
    ).toHaveValue("操作");
    expect(
      screen.getByRole("combobox", { name: "教育阶段筛选" }),
    ).toHaveTextContent("本科");
    expect(
      screen.getByRole("combobox", { name: "课程类型筛选" }),
    ).toHaveTextContent("专业课");
    expect(requestedUrl?.searchParams.get("q")).toBe("操作");
  });
});
