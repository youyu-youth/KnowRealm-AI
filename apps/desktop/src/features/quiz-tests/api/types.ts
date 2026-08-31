import type { components } from "@knowrealm/api-types";

export type QuizQuestionType = components["schemas"]["QuizQuestionType"];
export type QuizTestCreate = components["schemas"]["QuizTestCreateRequest"];
export type QuizTestCreated = components["schemas"]["QuizTestCreateOut"];
export type QuizTestList = components["schemas"]["QuizTestListOut"];
export type QuizTestDetail = components["schemas"]["QuizTestDetailOut"];
export type QuizTestSummary = components["schemas"]["QuizTestSummaryOut"];
export type QuizTestStatus = components["schemas"]["QuizTestStatus"];
export type QuizTestItem = components["schemas"]["QuizTestItemOut"];
export type QuizTestItemResult = NonNullable<QuizTestItem["result"]>;
export type QuizTestAnswerRequest =
  components["schemas"]["QuizTestAnswerRequest"];
export type QuizTestAnswer = QuizTestAnswerRequest["answer"];

export const QUIZ_QUESTION_TYPES: QuizQuestionType[] = [
  "MULTIPLE_CHOICE",
  "MULTIPLE_SELECT",
  "TRUE_FALSE",
  "FILL_BLANK",
  "SHORT_ANSWER",
];

export const TEST_VIEWS = ["single", "sectioned", "full"] as const;
export type TestView = (typeof TEST_VIEWS)[number];

/** 卷面 URL `?view=` 参数的三档展示形式；缺失或非法值回落单题档 */
export function asTestView(value: unknown): TestView {
  return TEST_VIEWS.includes(value as TestView)
    ? (value as TestView)
    : "single";
}
