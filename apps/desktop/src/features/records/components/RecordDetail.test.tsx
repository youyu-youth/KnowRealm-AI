// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const ROUTE_PATH = `/records/${RECORD_ID}`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: COURSE_ID,
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "SUMMARY_PENDING",
  duration_ms: 65_000,
  summary_confirmed_at: null,
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-19T08:30:00.000000Z",
};

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

function renderAt(path = ROUTE_PATH) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

describe("学习记录详情", () => {
  it("可直接打开并在刷新后从详情接口恢复真实元数据", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, ({ request }) => {
        calls += 1;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(record);
      }),
    );

    renderAt();
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();
    expect(screen.getByText("音频导入")).toBeInTheDocument();
    expect(screen.getByText("等待生成总结")).toBeInTheDocument();
    expect(screen.getByText("1 分 5 秒")).toBeInTheDocument();

    cleanup();
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("加载失败可重试，404 则显示不存在状态", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json(record);
      }),
    );
    renderAt();

    expect(
      await screen.findByRole(
        "heading",
        { name: "学习记录暂时无法读取" },
        { timeout: 6_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("学习记录暂时无法读取");
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      await screen.findByRole("heading", { name: "操作系统第一讲" }),
    ).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学习记录不存在或已删除" },
          { status: 404 },
        ),
      ),
    );
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "学习记录不存在或已删除" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "学习记录不存在或已删除",
    );
    expect(screen.getByRole("link", { name: "返回知识空间" })).toHaveAttribute(
      "href",
      "/spaces",
    );
  });

  it("加载期间不闪现空态，Summary 诚实为空且其余资产页签禁用", async () => {
    server.use(
      http.get(DETAIL_URL, async () => {
        await delay(200);
        return HttpResponse.json(record);
      }),
    );
    renderAt();

    expect(await screen.findByText("正在读取学习记录详情")).toHaveAttribute(
      "role",
      "status",
    );
    expect(screen.queryByText("还没有生成总结")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "还没有生成总结" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    for (const label of [
      "Transcript",
      "Highlights",
      "Notes",
      "Flashcards",
      "Quiz",
    ]) {
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      expect(screen.getByRole("tab", { name: label })).toHaveAttribute(
        "tabindex",
        "-1",
      );
    }
    expect(screen.getByText("其余学习资产尚未接入")).toBeInTheDocument();
    expect(screen.queryByText(/示例总结/)).not.toBeInTheDocument();
  });

  it("返回路径由真实课程归属决定，空课程归属返回知识空间", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(record)));
    renderAt();

    expect(
      await screen.findByRole("link", { name: "返回课程学习记录" }),
    ).toHaveAttribute("href", `/spaces/${COURSE_ID}?tab=records`);

    cleanup();
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, course_id: null, title: "   " }),
      ),
    );
    renderAt();
    expect(
      await screen.findByRole("heading", { name: "未命名学习记录" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "返回知识空间" }),
    ).toHaveAttribute("href", "/spaces");
  });

  it("FAILED 只显示通用失败说明且没有伪造恢复动作", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ ...record, status: "FAILED" }),
      ),
    );
    renderAt();

    expect(await screen.findByText("学习记录处理失败")).toBeInTheDocument();
    expect(screen.getByText("当前暂无可用恢复操作。")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /重试|恢复/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/error|code|任务/)).not.toBeInTheDocument();
  });
});
