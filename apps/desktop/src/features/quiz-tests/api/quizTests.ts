import { apiFetch } from "@/services/http/client";
import type {
  QuizTestCreate,
  QuizTestCreated,
  QuizTestDetail,
  QuizTestList,
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
};
