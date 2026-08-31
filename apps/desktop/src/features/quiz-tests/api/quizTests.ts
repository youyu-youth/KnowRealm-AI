import { apiFetch } from "@/services/http/client";
import type {
  QuizTestAnswerRequest,
  QuizTestCreate,
  QuizTestCreated,
  QuizTestDetail,
  QuizTestList,
  QuizTestSummary,
} from "@/features/quiz-tests/api/types";

export const quizTestApi = {
  list: (courseId: string) =>
    apiFetch<QuizTestList>(`/api/courses/${courseId}/quiz-tests`),
  create: (courseId: string, payload: QuizTestCreate) =>
    apiFetch<QuizTestCreated>(`/api/courses/${courseId}/quiz-tests`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  get: (testId: string) =>
    apiFetch<QuizTestDetail>(`/api/quiz-tests/${testId}`),
  answer: (testId: string, payload: QuizTestAnswerRequest) =>
    apiFetch<QuizTestDetail>(`/api/quiz-tests/${testId}/answers`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submit: (testId: string) =>
    apiFetch<QuizTestDetail>(`/api/quiz-tests/${testId}/submit`, {
      method: "POST",
    }),
  regrade: (testId: string) =>
    apiFetch<QuizTestDetail>(`/api/quiz-tests/${testId}/regrade`, {
      method: "POST",
    }),
  abandon: (testId: string) =>
    apiFetch<QuizTestSummary>(`/api/quiz-tests/${testId}/abandon`, {
      method: "POST",
    }),
};
