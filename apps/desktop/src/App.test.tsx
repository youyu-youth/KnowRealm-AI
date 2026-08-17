// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";

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
    expect(screen.getByRole("button", { name: "新建知识空间" })).toBeDisabled();
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
});
