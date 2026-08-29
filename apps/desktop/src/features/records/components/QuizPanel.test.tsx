// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const ROUTE_PATH = `/records/${RECORD_ID}`;
const JOB_ID = "33333333-3333-4333-8333-333333333333";
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const QUIZZES_URL = `${DETAIL_URL}/quizzes`;
const QUIZ_JOBS_URL = `${DETAIL_URL}/quiz-jobs`;
const QUIZ_BATCH_CONFIRMATIONS_URL = `${DETAIL_URL}/quiz-batches/${JOB_ID}/confirmations`;
const QUIZ_BATCH_DISCARDS_URL = `${DETAIL_URL}/quiz-batches/${JOB_ID}/discards`;
const PREFERENCES_URL = `${TEST_SIDECAR_URL}/api/settings/preferences`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;

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
window.Element.prototype.scrollIntoView = vi.fn();

beforeEach(() => {
  server.use(
    http.get(SUMMARY_URL, () =>
      HttpResponse.json({
        action_required: "GENERATE",
        active_job_id: null,
        blocked_reason: null,
        summary: null,
      }),
    ),
    http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path = ROUTE_PATH) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

function quizItem(
  overrides: Partial<components["schemas"]["QuizOut"]> = {},
): components["schemas"]["QuizOut"] {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    record_id: RECORD_ID,
    batch_id: JOB_ID,
    generated_from_summary_id: "55555555-5555-4555-8555-555555555555",
    generation_status: "DRAFT",
    question_type: "MULTIPLE_CHOICE",
    stem: "进程调度的基本功能是什么？",
    options: [
      "选择就绪进程分配处理器",
      "管理内存分配",
      "处理外部中断",
      "维护文件系统",
    ],
    correct_answer: 0,
    explanation: "进程调度决定哪个就绪进程获得处理器。",
    difficulty: "EASY",
    user_answer: null,
    answer_result: null,
    answered_at: null,
    created_at: "2026-08-25T12:00:00.000000Z",
    updated_at: "2026-08-25T12:00:00.000000Z",
    ...overrides,
  };
}

function quizReadOut(
  overrides: Partial<components["schemas"]["QuizReadOut"]> = {},
): components["schemas"]["QuizReadOut"] {
  return {
    items: [],
    action_required: "GENERATE",
    active_job_id: null,
    blocked_reason: null,
    ...overrides,
  };
}

function preferencesOut(
  overrides: Partial<components["schemas"]["PreferencesOut"]> = {},
): components["schemas"]["PreferencesOut"] {
  return {
    theme: "SYSTEM",
    font_scale: "M",
    timezone: null,
    quiz_last_count: 5,
    ...overrides,
  };
}

function activateQuiz(
  item: components["schemas"]["QuizOut"],
): components["schemas"]["QuizOut"] {
  return { ...item, generation_status: "ACTIVE" };
}

function readObjectiveAnswer(body: unknown): number {
  if (
    typeof body !== "object" ||
    body === null ||
    !("answer" in body) ||
    typeof body.answer !== "number"
  ) {
    throw new Error("客观题作答请求缺少数字 answer");
  }
  return body.answer;
}

function readShortAnswer(body: unknown): string {
  if (
    typeof body !== "object" ||
    body === null ||
    !("answer" in body) ||
    typeof body.answer !== "string"
  ) {
    throw new Error("简答题作答请求缺少字符串 answer");
  }
  return body.answer;
}

function readSelfAssessment(body: unknown): "CORRECT" | "WRONG" {
  if (
    typeof body !== "object" ||
    body === null ||
    !("result" in body) ||
    (body.result !== "CORRECT" && body.result !== "WRONG")
  ) {
    throw new Error("简答题自评请求缺少二态 result");
  }
  return body.result;
}

const completedRecord: RecordOut = {
  ...record,
  status: "COMPLETED",
  summary_confirmed_at: "2026-08-24T12:00:00.000000Z",
};

describe("习题页签", () => {
  it("未完成记录页签禁用，完成后未确认总结则引导去总结页签", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(record)),
      http.get(QUIZZES_URL, () => HttpResponse.json(quizReadOut())),
    );
    renderAt(ROUTE_PATH);

    const quizTab = await screen.findByRole("tab", { name: "习题" });
    expect(quizTab).toHaveAttribute("aria-disabled", "true");

    cleanup();
    window.history.replaceState(null, "", "/");
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          quizReadOut({
            action_required: "NONE",
            blocked_reason: "SUMMARY_NOT_CONFIRMED",
          }),
        ),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(
      await screen.findByRole("heading", { name: "先确认总结，再生成习题" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "查看总结" }));
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("生成对话框默认读取偏好档位，取消题型阻止提交，成功后写回偏好并进入进行中态", async () => {
    let generating = false;
    const submittedBodies: unknown[] = [];
    const preferenceBodies: unknown[] = [];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          generating
            ? quizReadOut({ action_required: "NONE", active_job_id: JOB_ID })
            : quizReadOut(),
        ),
      ),
      http.get(PREFERENCES_URL, () =>
        HttpResponse.json(preferencesOut({ quiz_last_count: 3 })),
      ),
      http.put(PREFERENCES_URL, async ({ request }) => {
        preferenceBodies.push(await request.json());
        return HttpResponse.json(preferencesOut({ quiz_last_count: 3 }));
      }),
      http.post(QUIZ_JOBS_URL, async ({ request }) => {
        submittedBodies.push(await request.json());
        generating = true;
        return HttpResponse.json({ job_id: JOB_ID }, { status: 202 });
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    fireEvent.click(await screen.findByRole("button", { name: "生成习题" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeVisible();
    expect(
      screen.getByRole("checkbox", { name: "选择题", checked: true }),
    ).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "简答题" })).toBeVisible();
    expect(
      screen.getByRole("radio", { name: "3", checked: true }),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("radio", { name: "10" }));
    expect(
      screen.getByRole("radio", { name: "10", checked: true }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("checkbox", { name: "简答题" }));
    const submit = screen.getByRole("button", { name: "开始生成" });
    fireEvent.click(submit);

    expect(await screen.findByText("正在生成习题候选")).toBeVisible();
    expect(submittedBodies).toEqual([
      {
        question_types: ["MULTIPLE_CHOICE", "TRUE_FALSE"],
        total_count: 10,
      },
    ]);
    expect(preferenceBodies).toEqual([{ quiz_last_count: 10 }]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("候选只读审阅展示答案与解析，二次确认丢弃后回到可生成态", async () => {
    let discarded = false;
    let discardCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          discarded
            ? quizReadOut()
            : quizReadOut({
                action_required: "ADOPT",
                items: [
                  quizItem(),
                  quizItem({
                    id: "77777777-7777-4777-8777-777777777777",
                    question_type: "TRUE_FALSE",
                    stem: "时间片越小，系统效率越高。",
                    options: ["对", "错"],
                    correct_answer: 1,
                    explanation: "时间片过小会导致上下文切换开销过大。",
                    difficulty: "MEDIUM",
                  }),
                ],
              }),
        ),
      ),
      http.post(QUIZ_BATCH_DISCARDS_URL, () => {
        discardCalls += 1;
        discarded = true;
        return HttpResponse.json(quizReadOut());
      }),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(
      await screen.findByRole("heading", { name: "习题候选（只读）" }),
    ).toBeVisible();
    expect(screen.getByText("共 2 题，基于当前已确认的总结生成")).toBeVisible();
    expect(
      screen.getByText("正确答案：A. 选择就绪进程分配处理器"),
    ).toBeVisible();
    expect(
      screen.getByText("解析：进程调度决定哪个就绪进程获得处理器。"),
    ).toBeVisible();
    expect(
      screen.getByText("解析：时间片过小会导致上下文切换开销过大。"),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "丢弃本批候选" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认丢弃" }));

    expect(
      await screen.findByRole("button", { name: "生成习题" }),
    ).toBeVisible();
    expect(discardCalls).toBe(1);
  });

  it("采用前提示旧批未完成数，采用后旧批退出且新批平滑进入", async () => {
    const oldBatchId = "88888888-8888-4888-8888-888888888888";
    let adopted = false;
    let adoptionCalls = 0;
    const candidateItems = [
      quizItem(),
      quizItem({
        id: "77777777-7777-4777-8777-777777777777",
        question_type: "TRUE_FALSE",
        stem: "时间片越小，系统效率越高。",
        options: ["对", "错"],
        correct_answer: 1,
        explanation: "时间片过小会导致上下文切换开销过大。",
        difficulty: "MEDIUM",
      }),
    ];
    const activeItems = [
      quizItem({
        id: "99999999-9999-4999-8999-999999999991",
        batch_id: oldBatchId,
        generation_status: "ACTIVE",
        stem: "旧批已完成题",
        user_answer: 0,
        answer_result: "CORRECT",
        answered_at: "2026-08-25T13:00:00.000000Z",
      }),
      quizItem({
        id: "99999999-9999-4999-8999-999999999992",
        batch_id: oldBatchId,
        generation_status: "ACTIVE",
        stem: "旧批未完成题",
      }),
    ];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          adopted
            ? quizReadOut({
                action_required: "GENERATE",
                items: candidateItems.map(activateQuiz),
              })
            : quizReadOut({
                action_required: "ADOPT",
                items: [...activeItems, ...candidateItems],
              }),
        ),
      ),
      http.post(QUIZ_BATCH_CONFIRMATIONS_URL, () => {
        adoptionCalls += 1;
        adopted = true;
        return HttpResponse.json(
          quizReadOut({
            action_required: "GENERATE",
            items: candidateItems.map(activateQuiz),
          }),
        );
      }),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(
      await screen.findByRole("heading", { name: "已采用习题" }),
    ).toBeVisible();
    expect(screen.getByText("旧批未完成题")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "采用本批" }));

    expect(
      await screen.findByRole("dialog", { name: "采用这批习题？" }),
    ).toBeVisible();
    expect(screen.getByText(/旧批次仍有 1 题未作答/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "确认采用" }));

    await waitFor(() =>
      expect(screen.queryByText("旧批未完成题")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("进程调度的基本功能是什么？")).toBeVisible();
    expect(screen.getByRole("button", { name: "再生成一批" })).toBeVisible();
    expect(adoptionCalls).toBe(1);
  });

  it("换代候选采用失败后关闭弹窗并引导丢弃重生成", async () => {
    let stale = false;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          quizReadOut({
            action_required: stale ? "NONE" : "ADOPT",
            blocked_reason: stale ? "SUMMARY_SUPERSEDED" : null,
            items: [quizItem()],
          }),
        ),
      ),
      http.post(QUIZ_BATCH_CONFIRMATIONS_URL, () => {
        stale = true;
        return HttpResponse.json(
          {
            detail: "总结已换代，请丢弃当前候选后重新生成",
            blocked_reason: "SUMMARY_SUPERSEDED",
          },
          { status: 409 },
        );
      }),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    fireEvent.click(await screen.findByRole("button", { name: "采用本批" }));
    fireEvent.click(screen.getByRole("button", { name: "确认采用" }));

    expect(
      await screen.findByRole("heading", {
        name: "总结已更新，请重新生成习题",
      }),
    ).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "采用本批" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "丢弃本批候选" })).toBeVisible();
  });

  it("选择题与判断题提交后即时判分并锁定展示答案解析", async () => {
    const submitted: Array<{ quizId: string; body: object }> = [];
    let quizReads = 0;
    const choice = quizItem({ generation_status: "ACTIVE" });
    const trueFalse = quizItem({
      id: "77777777-7777-4777-8777-777777777777",
      generation_status: "ACTIVE",
      question_type: "TRUE_FALSE",
      stem: "时间片越小，系统效率越高。",
      options: ["对", "错"],
      correct_answer: 1,
      explanation: "时间片过小会导致上下文切换开销过大。",
      difficulty: "MEDIUM",
    });
    let items = [choice, trueFalse];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () => {
        quizReads += 1;
        return HttpResponse.json(
          quizReadOut({
            action_required: "GENERATE",
            items,
          }),
        );
      }),
      http.post(
        `${QUIZZES_URL}/:quizId/answers`,
        async ({ params, request }) => {
          const answer = readObjectiveAnswer(await request.json());
          const item = params.quizId === choice.id ? choice : trueFalse;
          submitted.push({ quizId: String(params.quizId), body: { answer } });
          await delay(100);
          const answered: components["schemas"]["QuizOut"] = {
            ...item,
            user_answer: answer,
            answer_result: answer === item.correct_answer ? "CORRECT" : "WRONG",
            answered_at: "2026-08-25T13:00:00.000000Z",
            updated_at: "2026-08-25T13:00:00.000000Z",
          };
          items = items.map((current) =>
            current.id === answered.id ? answered : current,
          );
          return HttpResponse.json(answered);
        },
      ),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(await screen.findByText(choice.stem)).toBeVisible();
    expect(screen.queryByText(/正确答案：/)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("radio", { name: `C. ${choice.options[2]}` }),
    );
    fireEvent.click(screen.getAllByRole("button", { name: "提交答案" })[0]);
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "提交答案" })[1],
      ).toBeDisabled(),
    );
    expect(screen.getByRole("radio", { name: "错" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );

    expect(await screen.findByText("回答错误")).toBeVisible();
    await waitFor(() => expect(quizReads).toBeGreaterThan(1));
    expect(
      screen.getByText("正确答案：A. 选择就绪进程分配处理器"),
    ).toBeVisible();
    expect(
      screen.getByText("解析：进程调度决定哪个就绪进程获得处理器。"),
    ).toBeVisible();
    expect(
      screen.getByRole("radio", { name: `C. ${choice.options[2]}` }),
    ).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(screen.getByRole("radio", { name: "错" }));
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(await screen.findByText("回答正确")).toBeVisible();
    expect(screen.getByText("正确答案：错")).toBeVisible();
    expect(submitted).toEqual([
      { quizId: choice.id, body: { answer: 2 } },
      { quizId: trueFalse.id, body: { answer: 1 } },
    ]);
  });

  it("简答提交后显示参考答案并自评，全部完成后展示答对计数", async () => {
    const referenceAnswer =
      "调度器按照策略从就绪队列中选择下一个占用处理器的进程。";
    const choice = quizItem({
      generation_status: "ACTIVE",
      user_answer: 0,
      answer_result: "CORRECT",
      answered_at: "2026-08-25T13:00:00.000000Z",
    });
    const trueFalse = quizItem({
      id: "77777777-7777-4777-8777-777777777777",
      generation_status: "ACTIVE",
      question_type: "TRUE_FALSE",
      stem: "时间片越小，系统效率越高。",
      options: ["对", "错"],
      correct_answer: 1,
      explanation: "时间片过小会导致上下文切换开销过大。",
      difficulty: "MEDIUM",
      user_answer: 0,
      answer_result: "WRONG",
      answered_at: "2026-08-25T13:01:00.000000Z",
    });
    let short = quizItem({
      id: "88888888-8888-4888-8888-888888888888",
      generation_status: "ACTIVE",
      question_type: "SHORT_ANSWER",
      stem: "简述进程调度器的职责。",
      options: [],
      correct_answer: null,
      explanation: null,
      difficulty: "MEDIUM",
    });
    let items = [choice, trueFalse, short];
    const submitted: object[] = [];
    const assessed: object[] = [];
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(quizReadOut({ action_required: "GENERATE", items })),
      ),
      http.post(`${QUIZZES_URL}/:quizId/answers`, async ({ request }) => {
        const answer = readShortAnswer(await request.json());
        submitted.push({ answer });
        short = {
          ...short,
          correct_answer: referenceAnswer,
          explanation: "调度器负责就绪队列管理与处理器时间分配。",
          user_answer: answer,
          answered_at: "2026-08-25T13:02:00.000000Z",
        };
        items = [choice, trueFalse, short];
        return HttpResponse.json(short);
      }),
      http.post(
        `${QUIZZES_URL}/:quizId/self-assessments`,
        async ({ request }) => {
          const result = readSelfAssessment(await request.json());
          assessed.push({ result });
          short = { ...short, answer_result: result };
          items = [choice, trueFalse, short];
          return HttpResponse.json(short);
        },
      ),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(await screen.findByText(short.stem)).toBeVisible();
    const answer = screen.getByRole("textbox", { name: "你的作答" });
    expect(answer).toHaveAttribute("maxlength", "2000");
    expect(screen.getByRole("button", { name: "提交作答" })).toBeDisabled();
    expect(screen.queryByText(/参考答案：/)).not.toBeInTheDocument();

    fireEvent.change(answer, {
      target: { value: "调度器从就绪队列中选择下一个进程。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交作答" }));

    expect(
      await screen.findByText(`参考答案：${referenceAnswer}`),
    ).toBeVisible();
    expect(screen.getByText("待自评")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "你的作答" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "自评正确" }));

    expect(
      await screen.findByRole("heading", { name: "本批练习已完成" }),
    ).toBeVisible();
    expect(screen.getByText("答对 2 / 3")).toBeVisible();
    expect(submitted).toEqual([
      { answer: "调度器从就绪队列中选择下一个进程。" },
    ]);
    expect(assessed).toEqual([{ result: "CORRECT" }]);
  });

  it("总结换代后 ACTIVE 客观题仍可继续作答", async () => {
    let active = quizItem({
      generation_status: "ACTIVE",
      correct_answer: null,
      explanation: null,
    });
    let submitCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          quizReadOut({
            action_required: "NONE",
            blocked_reason: "SUMMARY_SUPERSEDED",
            items: [active],
          }),
        ),
      ),
      http.post(`${QUIZZES_URL}/:quizId/answers`, async ({ request }) => {
        const answer = readObjectiveAnswer(await request.json());
        submitCalls += 1;
        active = {
          ...active,
          correct_answer: 0,
          explanation: "进程调度决定哪个就绪进程获得处理器。",
          user_answer: answer,
          answer_result: answer === 0 ? "CORRECT" : "WRONG",
          answered_at: "2026-08-25T13:00:00.000000Z",
        };
        return HttpResponse.json(active);
      }),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(await screen.findByText(active.stem)).toBeVisible();
    expect(screen.queryByText(/正确答案：/)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("radio", { name: "A. 选择就绪进程分配处理器" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText("回答正确")).toBeVisible();
    expect(
      screen.getByText("正确答案：A. 选择就绪进程分配处理器"),
    ).toBeVisible();
    expect(submitCalls).toBe(1);
  });

  it("重进习题页后恢复已答选择与只读反馈", async () => {
    const answered = quizItem({
      generation_status: "ACTIVE",
      user_answer: 0,
      answer_result: "CORRECT",
      answered_at: "2026-08-25T13:00:00.000000Z",
    });
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(
          quizReadOut({ action_required: "GENERATE", items: [answered] }),
        ),
      ),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(
      await screen.findByRole("radio", {
        name: "A. 选择就绪进程分配处理器",
        checked: true,
      }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("回答正确")).toBeVisible();
    expect(
      screen.getByText("正确答案：A. 选择就绪进程分配处理器"),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "提交答案" }),
    ).not.toBeInTheDocument();
  });

  it("生成失败展示可重试状态", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(completedRecord)),
      http.get(QUIZZES_URL, () =>
        HttpResponse.json(quizReadOut({ action_required: "RETRY" })),
      ),
      http.get(PREFERENCES_URL, () => HttpResponse.json(preferencesOut())),
    );
    renderAt(`${ROUTE_PATH}?tab=quiz`);

    expect(await screen.findByText("上次生成没有成功")).toBeVisible();
    expect(screen.getByRole("button", { name: "重新生成" })).toBeVisible();
  });
});
