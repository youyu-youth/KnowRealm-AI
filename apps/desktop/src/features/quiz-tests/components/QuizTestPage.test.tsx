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
type QuizTestDetail = components["schemas"]["QuizTestDetailOut"];
type QuizTestItem = components["schemas"]["QuizTestItemOut"];
type QuizTestSummary = components["schemas"]["QuizTestSummaryOut"];

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const TEST_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const TEST_URL = `${TEST_SIDECAR_URL}/api/quiz-tests/${TEST_ID}`;
const ANSWERS_URL = `${TEST_URL}/answers`;
const ABANDON_URL = `${TEST_URL}/abandon`;
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

const summary: QuizTestSummary = {
  id: TEST_ID,
  course_id: COURSE_ID,
  record_id: null,
  mode: "MOCK",
  status: "IN_PROGRESS",
  score: null,
  total_count: 3,
  answered_count: 0,
  started_at: "2026-08-31T08:00:00.000000Z",
  completed_at: null,
  created_at: "2026-08-31T08:00:00.000000Z",
  updated_at: "2026-08-31T08:00:00.000000Z",
};

const mcItem: QuizTestItem = {
  id: "item-1",
  quiz_id: "quiz-1",
  sequence_no: 1,
  question_type: "MULTIPLE_CHOICE",
  stem: "进程调度的核心职责是什么？",
  options: ["选择就绪进程", "分配内存"],
  difficulty: "EASY",
  user_answer: null,
  result: null,
  score: null,
  answered_at: null,
};

const fillBlankItem: QuizTestItem = {
  id: "item-2",
  quiz_id: "quiz-2",
  sequence_no: 2,
  question_type: "FILL_BLANK",
  stem: "线程是____的调度单位。",
  options: [],
  difficulty: "MEDIUM",
  user_answer: null,
  result: null,
  score: null,
  answered_at: null,
};

const shortItem: QuizTestItem = {
  id: "item-3",
  quiz_id: "quiz-3",
  sequence_no: 3,
  question_type: "SHORT_ANSWER",
  stem: "简述时间片轮转。",
  options: [],
  difficulty: "MEDIUM",
  user_answer: null,
  result: null,
  score: null,
  answered_at: null,
};

const detail: QuizTestDetail = {
  ...summary,
  items: [mcItem, fillBlankItem, shortItem],
};

function answeredMc(): QuizTestDetail {
  return {
    ...detail,
    answered_count: 1,
    items: [
      {
        ...mcItem,
        user_answer: 1,
        result: "WRONG",
        score: 0,
        answered_at: "2026-08-31T08:01:00.000000Z",
      },
      fillBlankItem,
      shortItem,
    ],
  };
}

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

function mockPaper(response: QuizTestDetail = detail) {
  return server.use(
    http.get(COURSE_URL, () => HttpResponse.json(course)),
    http.get(TESTS_URL, () =>
      HttpResponse.json({ items: [summary], blocked_reason: null }),
    ),
    http.get(TEST_URL, () => HttpResponse.json(response)),
    // AppShell 在路由切换时回写 last_route
    http.put(`${TEST_SIDECAR_URL}/api/settings/preferences`, () =>
      HttpResponse.json({
        theme: "SYSTEM",
        font_scale: "M",
        timezone: null,
        close_behavior: "TRAY",
        quick_note_shortcut: "Ctrl+Alt+N",
        autostart: false,
        quiz_last_count: 5,
      }),
    ),
  );
}

describe("模拟测试卷面作答", () => {
  it("三档展示形式随切且 view 同步到 URL", async () => {
    mockPaper();
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    expect(await screen.findByText(mcItem.stem)).toBeInTheDocument();
    expect(screen.queryByText(shortItem.stem)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "分段" }));
    expect(await screen.findByText("一、单选题")).toBeInTheDocument();
    expect(window.location.search).toContain("view=sectioned");
    // 分段档默认停在第一段（单选题），其他段不渲染
    expect(screen.getByText(mcItem.stem)).toBeInTheDocument();
    expect(screen.queryByText(shortItem.stem)).not.toBeInTheDocument();
    expect(screen.queryByText("二、填空题")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "整卷" }));
    // 等一个只在整卷档出现的标题，避免命中切换前已卸载的旧节点
    expect(await screen.findByText("二、填空题")).toBeInTheDocument();
    expect(screen.getByText("一、单选题")).toBeInTheDocument();
    expect(screen.getByText("三、简答题")).toBeInTheDocument();
    expect(screen.getByText("二、填空题")).toBeInTheDocument();
    expect(screen.getByText("三、简答题")).toBeInTheDocument();
    expect(screen.getByText(mcItem.stem)).toBeInTheDocument();
    expect(screen.getByText(shortItem.stem)).toBeInTheDocument();
    expect(window.location.search).toContain("view=full");
  });

  it("单题档键盘左右翻题、输入框聚焦时不拦截、答题卡格子可跳题", async () => {
    mockPaper();
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    await screen.findByText(mcItem.stem);
    expect(screen.getByText(/第 1 \/ 3 题/)).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByText(/第 2 \/ 3 题/)).toBeInTheDocument();

    const blankInput = screen.getByRole("textbox", { name: "第 1 空" });
    fireEvent.keyDown(blankInput, { key: "ArrowRight" });
    expect(screen.getByText(/第 2 \/ 3 题/)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "跳到第 3 题（简答题）" }),
    );
    expect(await screen.findByText(/第 3 \/ 3 题/)).toBeInTheDocument();
  });

  it("客观题提交即判并锁定，进度条与交卷按钮联动", async () => {
    let submitted: unknown;
    mockPaper();
    server.use(
      http.post(ANSWERS_URL, async ({ request }) => {
        submitted = await request.json();
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(answeredMc());
      }),
    );
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    await screen.findByText(mcItem.stem);
    expect(screen.getByText("已答 0 / 3")).toBeInTheDocument();
    expect(screen.getByText("全部作答后方可交卷")).toBeInTheDocument();

    const submit = screen.getAllByRole("button", { name: "交卷" });
    for (const button of submit) {
      expect(button).toBeDisabled();
    }

    fireEvent.click(screen.getByRole("radio", { name: "B. 分配内存" }));

    expect(await screen.findByText("答错")).toBeInTheDocument();
    expect(screen.getByText("已提交 · 一题一答，不可修改")).toBeInTheDocument();
    // 锁定后点击其他选项不改变选中、不重新提交
    fireEvent.click(screen.getByRole("radio", { name: "A. 选择就绪进程" }));
    expect(screen.getByRole("radio", { name: "B. 分配内存" })).toBeChecked();
    expect(submitted).toEqual({ item_id: mcItem.id, answer: 1 });
    expect(screen.getByText("已答 1 / 3")).toBeInTheDocument();

    for (const button of screen.getAllByRole("button", { name: "交卷" })) {
      expect(button).toBeDisabled();
    }
  });

  it("简答提交后锁定待评", async () => {
    const shortAnswered: QuizTestDetail = {
      ...detail,
      answered_count: 1,
      items: [
        mcItem,
        fillBlankItem,
        {
          ...shortItem,
          user_answer: "按时间片轮转调度。",
          answered_at: "2026-08-31T08:01:00.000000Z",
        },
      ],
    };
    mockPaper();
    server.use(http.post(ANSWERS_URL, () => HttpResponse.json(shortAnswered)));
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    fireEvent.click(
      await screen.findByRole("button", { name: "跳到第 3 题（简答题）" }),
    );
    const textarea = await screen.findByRole("textbox", {
      name: "第 3 题作答",
    });
    fireEvent.change(textarea, { target: { value: "按时间片轮转调度。" } });
    fireEvent.click(screen.getByRole("button", { name: "提交作答" }));

    expect(await screen.findByText("已提交 · 待 AI 评分")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "第 3 题作答" })).toBeDisabled();
  });

  it("中断重进：已答题锁定显示作答与判分，定位到第一道未答题", async () => {
    mockPaper(answeredMc());
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    expect(await screen.findByText("已答 1 / 3")).toBeInTheDocument();
    // 单题档初始定位到第一道未答题（第 2 题填空）
    expect(screen.getByText(/第 2 \/ 3 题/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "跳到第 1 题（单选题）" }),
    );
    expect(await screen.findByText("答错")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "B. 分配内存" })).toBeChecked();
    // 恢复后已答题仍锁定：点击其他选项不改变选中
    fireEvent.click(screen.getByRole("radio", { name: "A. 选择就绪进程" }));
    expect(screen.getByRole("radio", { name: "B. 分配内存" })).toBeChecked();
    expect(screen.getByText("已提交 · 一题一答，不可修改")).toBeInTheDocument();
  });

  it("放弃测试需确认，成功后回到课程模拟测试列表", async () => {
    let abandonCalled = false;
    mockPaper();
    server.use(
      http.post(ABANDON_URL, ({ request }) => {
        abandonCalled = true;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json({ ...summary, status: "ABANDONED" });
      }),
    );
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    fireEvent.click(await screen.findByRole("button", { name: "放弃测试" }));
    const dialog = screen.getByRole("dialog", {
      name: "放弃这次模拟测试？",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "确认放弃" }));

    expect(
      await screen.findByRole("list", { name: "模拟测试历史" }),
    ).toBeInTheDocument();
    expect(abandonCalled).toBe(true);
    expect(window.location.pathname).toBe(`/spaces/${COURSE_ID}`);
  });
});
