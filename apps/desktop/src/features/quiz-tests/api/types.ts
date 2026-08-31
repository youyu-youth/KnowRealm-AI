import type { components } from "@knowrealm/api-types";

export type QuizQuestionType = components["schemas"]["QuizQuestionType"];
export type QuizTestCreate = components["schemas"]["QuizTestCreateRequest"];
export type QuizTestCreated = components["schemas"]["QuizTestCreateOut"];
export type QuizTestList = components["schemas"]["QuizTestListOut"];
export type QuizTestDetail = components["schemas"]["QuizTestDetailOut"];
export type QuizTestStatus = components["schemas"]["QuizTestStatus"];

export const QUIZ_QUESTION_TYPES: QuizQuestionType[] = [
  "MULTIPLE_CHOICE",
  "MULTIPLE_SELECT",
  "TRUE_FALSE",
  "FILL_BLANK",
  "SHORT_ANSWER",
];
