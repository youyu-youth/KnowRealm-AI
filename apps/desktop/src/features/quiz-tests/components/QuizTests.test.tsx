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
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type QuizTestSummary = components["schemas"]["QuizTestSummaryOut"];
type QuizTestDetail = components["schemas"]["QuizTestDetailOut"];

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const TEST_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const TESTS_URL = `${COURSE_URL}/quiz-tests`;

const course: CourseDetail = {
  id: COURSE_ID,
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: null,
  status: "ACTIVE",
  hot_words: [],
  created_at: "2026-08-17T00:00:00.000000Z",
  updated_at: "2026-08-18T00:00:00.000000Z",
};

function summary(
  status: QuizTestSummary["status"],
  index: number,
): QuizTestSummary {
  return {
    id: `22222222-2222-4222-8222-${String(index).padStart(12, "0")}`,
    course_id: COURSE_ID,
    record_id: null,
    mode: "MOCK",
    status,
    score: status === "COMPLETED" ? 0.8 : null,
    total_count: 5,
    answered_count: status === "IN_PROGRESS" ? 2 : 5,
    started_at: `2026-08-${30 - index}T08:00:00.000000Z`,
    completed_at:
      status === "COMPLETED" ? `2026-08-${30 - index}T08:10:00.000000Z` : null,
    created_at: `2026-08-${30 - index}T08:00:00.000000Z`,
    updated_at: `2026-08-${30 - index}T08:10:00.000000Z`,
  };
}

const detail: QuizTestDetail = {
  ...summary("IN_PROGRESS", 1),
  id: TEST_ID,
  total_count: 2,
  answered_count: 0,
  items: [
    {
      id: "item-1",
      quiz_id: "quiz-1",
      record_id: "record-1",
      sequence_no: 1,
      question_type: "MULTIPLE_CHOICE",
      stem: "进程调度的核心职责是什么？",
      options: ["选择就绪进程", "分配文件空间"],
      difficulty: "EASY",
      user_answer: null,
      result: null,
      score: null,
      answered_at: null,
    },
    {
      id: "item-2",
      quiz_id: "quiz-2",
      record_id: "record-1",
      sequence_no: 2,
      question_type: "SHORT_ANSWER",
      stem: "简述时间片轮转。",
      options: [],
      difficulty: "MEDIUM",
      user_answer: null,
      result: null,
      score: null,
      answered_at: null,
    },
  ],
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

function renderAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

describe("模拟测试创建与只读卷面", () => {
  it("课程第三个 tab 从 URL 恢复并显示进行中、已完成、已放弃历史", async () => {
    server.use(
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(TESTS_URL, () =>
        HttpResponse.json({
          items: [
            summary("IN_PROGRESS", 1),
            summary("COMPLETED", 2),
            summary("ABANDONED", 3),
          ],
          blocked_reason: null,
        }),
      ),
    );

    renderAt(`/spaces/${COURSE_ID}?tab=tests`);

    const list = await screen.findByRole("list", { name: "模拟测试历史" });
    expect(within(list).getByText("进行中")).toBeInTheDocument();
    expect(within(list).getByText("已完成")).toBeInTheDocument();
    expect(within(list).getByText("已放弃")).toBeInTheDocument();
    expect(within(list).getAllByRole("link")[0]).toHaveAttribute(
      "href",
      `/spaces/${COURSE_ID}/tests/${summary("IN_PROGRESS", 1).id}`,
    );
  });

  it("五型多选与题量档创建后跳转，只抽到两题时在卷面提示不足", async () => {
    let requestBody: unknown;
    server.use(
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(TESTS_URL, () =>
        HttpResponse.json({ items: [], blocked_reason: null }),
      ),
      http.post(TESTS_URL, async ({ request }) => {
        requestBody = await request.json();
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(
          {
            test: detail,
            requested_count: 10,
            selected_count: 2,
            shortage: true,
          },
          { status: 201 },
        );
      }),
      http.get(`${TEST_SIDECAR_URL}/api/quiz-tests/${TEST_ID}`, () =>
        HttpResponse.json(detail),
      ),
    );

    renderAt(`/spaces/${COURSE_ID}?tab=tests`);
    fireEvent.click(
      await screen.findByRole("button", { name: "开始模拟测试" }),
    );

    const dialog = screen.getByRole("dialog", { name: "组建模拟测试" });
    expect(
      within(dialog).getAllByRole("checkbox", { checked: true }),
    ).toHaveLength(5);
    fireEvent.click(within(dialog).getByRole("radio", { name: "10 题" }));
    fireEvent.click(
      within(dialog).getByRole("button", { name: "创建并查看试卷" }),
    );

    expect(
      await screen.findByText("题库中只有 2 道符合条件的习题，已全部选入。"),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe(
      `/spaces/${COURSE_ID}/tests/${TEST_ID}`,
    );
    expect(requestBody).toEqual({
      question_types: [
        "MULTIPLE_CHOICE",
        "MULTIPLE_SELECT",
        "TRUE_FALSE",
        "FILL_BLANK",
        "SHORT_ANSWER",
      ],
      total_count: 10,
    });
  });

  it("课程题库为空时显示专属空态且不开放组卷入口", async () => {
    server.use(
      http.get(COURSE_URL, () => HttpResponse.json(course)),
      http.get(TESTS_URL, () =>
        HttpResponse.json({
          items: [],
          blocked_reason: "NO_AVAILABLE_QUIZZES",
        }),
      ),
    );

    renderAt(`/spaces/${COURSE_ID}?tab=tests`);

    expect(
      await screen.findByRole("heading", { name: "课程题库还是空的" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "开始模拟测试" }),
    ).not.toBeInTheDocument();
  });

  it("进行中卷面可作答，ARCHIVED 课程读闸门禁止开始", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/quiz-tests/${TEST_ID}`, () =>
        HttpResponse.json(detail),
      ),
    );
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}`);

    expect(
      await screen.findByRole("heading", { name: "模拟测试" }),
    ).toBeInTheDocument();
    expect(screen.getByText("进程调度的核心职责是什么？")).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: "A. 选择就绪进程" }),
    ).toBeInTheDocument();
    expect(screen.getByText("已答 0 / 2")).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(COURSE_URL, () =>
        HttpResponse.json({ ...course, status: "ARCHIVED" }),
      ),
      http.get(TESTS_URL, () =>
        HttpResponse.json({ items: [], blocked_reason: "COURSE_ARCHIVED" }),
      ),
    );
    renderAt(`/spaces/${COURSE_ID}?tab=tests`);

    expect(
      await screen.findByText("已归档课程不能开始模拟测试"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "开始模拟测试" }),
    ).not.toBeInTheDocument();
  });
});
