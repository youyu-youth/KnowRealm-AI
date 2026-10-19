// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { selectSidebarCourses } from "@/components/layout/selectSidebarCourses";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

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

const AVATAR_URL = `${TEST_SIDECAR_URL}/api/profile/avatar`;
const LIBRARY_STATE_URL = `${TEST_SIDECAR_URL}/api/settings/data-directory/library-state`;
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3,
]);

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("侧边栏底部用户区", () => {
  it("课程保持更新时间顺序、当前课程置顶并限制五门", () => {
    const courses = Array.from({ length: 6 }, (_, index) => ({
      id: `course-${index}`,
      name: `课程 ${index}`,
      learning_context: "SCHOOL" as const,
      education_stage: "UNDERGRADUATE" as const,
      depth: null,
      course_type: "MAJOR" as const,
      description: null,
      status: "ACTIVE" as const,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: `2026-09-0${6 - index}T00:00:00Z`,
    }));

    expect(
      selectSidebarCourses(courses, "course-5").map((course) => course.id),
    ).toEqual(["course-5", "course-0", "course-1", "course-2", "course-3"]);
  });

  it("课程区可折叠，查询失败时在侧栏内降级", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json({ detail: "sidecar 抖动" }, { status: 500 }),
      ),
    );
    renderAt();

    const toggle = await screen.findByRole("button", { name: "近期课程" });
    expect(
      await screen.findByText("课程暂时不可用", undefined, { timeout: 8_000 }),
    ).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("课程暂时不可用")).not.toBeInTheDocument();
  }, 20_000);

  it("无昵称与头像时显示占位，点击跳设置页个人资料区", async () => {
    server.use(
      http.get(LIBRARY_STATE_URL, () =>
        HttpResponse.json({ empty_library: false }),
      ),
    );
    renderAt("/");

    const userArea = await screen.findByRole("link", {
      name: "打开档案设置",
    });
    expect(userArea).toHaveTextContent("未设置昵称");

    fireEvent.click(userArea);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "个人资料" })).toBeVisible(),
    );
    expect(screen.getByRole("link", { name: "学习画像" })).toHaveAttribute(
      "href",
      "/profile",
    );
  });

  it("有昵称与头像时同步展示", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/profile`, () =>
        HttpResponse.json({
          nickname: "阿邹",
          primary_role: "DEVELOPER",
          about_me: null,
        }),
      ),
      http.get(AVATAR_URL, () =>
        HttpResponse.arrayBuffer(PNG_BYTES, {
          headers: { "Content-Type": "image/png" },
        }),
      ),
    );

    renderAt("/");

    const userArea = await screen.findByRole("link", {
      name: "打开档案设置",
    });
    await waitFor(() => expect(userArea).toHaveTextContent("阿邹"));
    const sidebar = within(
      screen.getByRole("complementary", { name: "工作区导航" }),
    );
    await waitFor(() =>
      expect(sidebar.getByAltText("头像")).toBeInTheDocument(),
    );

    fireEvent.error(sidebar.getByAltText("头像"));
    expect(sidebar.getByRole("img", { name: "头像" })).toHaveTextContent("头");
  });
});
