// @vitest-environment jsdom

import type { components } from "@knowrealm/api-types";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

type Course = components["schemas"]["CourseOut"];

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

describe("首门课程持久化入口", () => {
  async function selectEducationStage() {
    const trigger = screen.getByRole("combobox", { name: "教育阶段" });
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: "本科" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() => expect(trigger).toHaveTextContent("本科"));
  }

  it("保存失败后保留输入并提供可重试错误", async () => {
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json({ detail: "本地服务暂时不可用" }, { status: 500 }),
      ),
    );
    renderWithQuery(<CoursesPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "新建知识空间" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectEducationStage();
    const submit = screen.getByRole("button", { name: "创建课程" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "本地服务暂时不可用",
    );
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统",
    );
  });

  it("携带启动令牌创建课程并立即刷新真实列表", async () => {
    const created: Course = {
      id: "11111111-1111-4111-8111-111111111111",
      name: "操作系统",
      learning_context: "SCHOOL",
      education_stage: "UNDERGRADUATE",
      depth: null,
      course_type: "MAJOR",
      description: null,
      status: "ACTIVE",
      created_at: "2026-08-17T00:00:00.000000Z",
      updated_at: "2026-08-17T00:00:00.000000Z",
    };
    let courses: Course[] = [];
    let receivedToken: string | null = null;
    let postCalls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json(courses),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        postCalls += 1;
        receivedToken = request.headers.get("X-KnowRealm-Token");
        courses = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderWithQuery(<CoursesPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "新建知识空间" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectEducationStage();
    const submit = screen.getByRole("button", { name: "创建课程" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(await screen.findByText("操作系统")).toBeInTheDocument();
    expect(receivedToken).toBe(TEST_LAUNCH_TOKEN);
    expect(postCalls).toBe(1);
  });
});
