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

const ANSWERED_AT = "2026-08-31T08:01:00.000000Z";

function answeredAllDetail(): QuizTestDetail {
  return {
    ...detail,
    answered_count: 3,
    items: [
      {
        ...mcItem,
        user_answer: 1,
        result: "WRONG",
        score: 0,
        answered_at: ANSWERED_AT,
      },
      {
        ...fillBlankItem,
        user_answer: ["16", "0.5"],
        result: "CORRECT",
        score: 1,
        answered_at: ANSWERED_AT,
      },
      {
        ...shortItem,
        user_answer: "按时间片轮转调度。",
        answered_at: ANSWERED_AT,
      },
    ],
  };
}

function completedDetail(): QuizTestDetail {
  return {
    ...summary,
    status: "COMPLETED",
    score: 0.37,
    total_count: 4,
    answered_count: 4,
    completed_at: "2026-08-31T08:10:00.000000Z",
    items: [
      {
        ...mcItem,
        user_answer: 0,
        result: "WRONG",
        score: 0,
        correct_answer: 1,
        explanation: "调度器职责解析。",
        answered_at: ANSWERED_AT,
      },
      {
        ...fillBlankItem,
        user_answer: ["16", "2"],
        result: "PARTIAL",
        score: 0.5,
        correct_answer: [["16"], ["1/2", "0.5"]],
        explanation: "第二空应为二分之一。",
        answered_at: ANSWERED_AT,
      },
      {
        ...shortItem,
        user_answer: "按时间片轮转调度。",
        result: "PARTIAL",
        score: 0.6,
        correct_answer: "参考答案文本",
        explanation: null,
        ai_grade: {
          verdict: "PARTIAL",
          score: 0.6,
          confidence: 0.4,
          rationale: "只答到一半。",
          error_code: null,
          needs_review: true,
        },
        answered_at: ANSWERED_AT,
      },
      {
        id: "item-4",
        quiz_id: "quiz-4",
        sequence_no: 4,
        question_type: "SHORT_ANSWER",
        stem: "简述死锁的四个必要条件。",
        options: [],
        difficulty: "HARD",
        user_answer: "互斥、持有等待。",
        result: null,
        score: null,
        correct_answer: "互斥、持有等待、不可剥夺、循环等待。",
        explanation: null,
        ai_grade: {
          verdict: null,
          score: null,
          confidence: null,
          rationale: null,
          error_code: "LLM_OUTPUT_INVALID",
          needs_review: false,
        },
        answered_at: ANSWERED_AT,
      },
    ],
  };
}

describe("交卷评分与结果页", () => {
  const SUBMIT_URL = `${TEST_URL}/submit`;
  const REGRADE_URL = `${TEST_URL}/regrade`;

  it("交卷需确认，提交后进入评分中状态", async () => {
    let submitCalled = false;
    mockPaper(answeredAllDetail());
    server.use(
      http.post(SUBMIT_URL, ({ request }) => {
        submitCalled = true;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json({ ...answeredAllDetail(), status: "GRADING" });
      }),
    );
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    fireEvent.click(
      (await screen.findAllByRole("button", { name: "交卷" }))[0],
    );
    const dialog = screen.getByRole("dialog", { name: "确认交卷？" });
    expect(
      within(dialog).getByText(/共 3 题，已答 3 题。客观题立即判分/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "确认交卷" }));

    // 确认交卷后弹窗立即关闭（不等请求返回），评分中状态随后到达
    expect(
      screen.queryByRole("dialog", { name: "确认交卷？" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText("本卷正在评分，评分完成后可查看成绩。"),
    ).toBeInTheDocument();
    expect(submitCalled).toBe(true);
  });

  it("未提交草稿切题后保留：填空与简答回看仍在", async () => {
    mockPaper();
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    fireEvent.click(
      await screen.findByRole("button", { name: "跳到第 2 题（填空题）" }),
    );
    const blankInput = await screen.findByRole("textbox", { name: "第 1 空" });
    fireEvent.change(blankInput, { target: { value: "就绪队列" } });

    fireEvent.keyDown(window, { key: "ArrowRight" });
    const textarea = await screen.findByRole("textbox", {
      name: "第 3 题作答",
    });
    fireEvent.change(textarea, { target: { value: "按时间片轮转调度。" } });

    // 翻回填空题：草稿仍在；再跳到简答题：草稿同样保留
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(
      (screen.getByRole("textbox", { name: "第 1 空" }) as HTMLInputElement)
        .value,
    ).toBe("就绪队列");
    fireEvent.click(
      screen.getByRole("button", { name: "跳到第 3 题（简答题）" }),
    );
    expect(
      (
        screen.getByRole("textbox", {
          name: "第 3 题作答",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("按时间片轮转调度。");
  });

  it("结果页展示批改与成绩摘要：得分、对错、低置信标记、未计分", async () => {
    mockPaper(completedDetail());
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=full`);

    expect(
      await screen.findByText("本卷已完成作答与评分。"),
    ).toBeInTheDocument();
    // 成绩摘要侧栏：得分 ×100 与对/错/半对/未计分/待复核计数
    expect(screen.getByText("37")).toBeInTheDocument();
    expect(screen.getByText("/ 100")).toBeInTheDocument();
    expect(screen.getByText("答对 0 · 答错 1 · 半对 2")).toBeInTheDocument();
    expect(
      screen.getByText("未计分 1（成绩为已计分 3 题的平均）"),
    ).toBeInTheDocument();
    expect(screen.getByText("建议人工复核 1 题")).toBeInTheDocument();

    // 客观题批改：你的作答 / 正确答案 / 解析
    expect(screen.getByText("你的作答：A. 选择就绪进程")).toBeInTheDocument();
    expect(screen.getByText("正确答案：B. 分配内存")).toBeInTheDocument();
    expect(screen.getByText("解析：调度器职责解析。")).toBeInTheDocument();
    // 填空逐空对错（文本跨 span 拆分，按分段断言）
    expect(screen.getByText(/第 1 空：/)).toBeInTheDocument();
    expect(screen.getByText(/✗（应为 1\/2）/)).toBeInTheDocument();
    // 简答评分依据、置信度、低置信标记与参考答案
    expect(screen.getByText("评分依据：只答到一半。")).toBeInTheDocument();
    expect(screen.getByText("得分 0.60")).toBeInTheDocument();
    expect(screen.getByText("置信度 0.40")).toBeInTheDocument();
    expect(screen.getByText("建议人工复核")).toBeInTheDocument();
    expect(screen.getByText("参考答案：参考答案文本")).toBeInTheDocument();
    // 评分失败题：未计分标注
    expect(
      screen.getByText("评分失败（LLM_OUTPUT_INVALID）· 未计分"),
    ).toBeInTheDocument();

    // 批改展示随三档形式走：切分段档仍渲染批改块（首段为单选题）
    fireEvent.click(screen.getByRole("tab", { name: "分段" }));
    // 分段档默认停首段：单选批改块仍在、简答段不渲染（证明切换生效且批改随档渲染）
    await screen.findByText("你的作答：A. 选择就绪进程");
    expect(screen.queryByText("简述死锁的四个必要条件。")).not.toBeTruthy();
  });

  it("评分失败态提供重新评分，成功后回到评分中", async () => {
    let regradeCalled = false;
    const failed: QuizTestDetail = {
      ...completedDetail(),
      status: "GRADING_FAILED",
      score: null,
    };
    mockPaper(failed);
    server.use(
      http.post(REGRADE_URL, ({ request }) => {
        regradeCalled = true;
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json({ ...failed, status: "GRADING" });
      }),
    );
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=single`);

    fireEvent.click(await screen.findByRole("button", { name: "重新评分" }));
    expect(
      await screen.findByText("本卷正在评分，评分完成后可查看成绩。"),
    ).toBeInTheDocument();
    expect(regradeCalled).toBe(true);
    // 已是评分中：重新评分入口消失
    expect(screen.queryByRole("button", { name: "重新评分" })).not.toBeTruthy();
  });

  it("已放弃的测试灰显横幅且不渲染批改块", async () => {
    mockPaper({
      ...answeredAllDetail(),
      status: "ABANDONED",
    });
    renderAt(`/spaces/${COURSE_ID}/tests/${TEST_ID}?view=full`);

    expect(
      await screen.findByText("本卷已放弃，仅供查看。"),
    ).toBeInTheDocument();
    // 放弃态不揭示答案：无正确答案批改行、无成绩摘要侧栏
    expect(screen.queryByText(/正确答案：/)).not.toBeTruthy();
    expect(screen.queryByText(/得分/)).not.toBeTruthy();
  });
});
