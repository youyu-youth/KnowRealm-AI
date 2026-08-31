export const quizTestKeys = {
  all: ["quiz-tests"] as const,
  list: (courseId: string) =>
    [...quizTestKeys.all, "course", courseId] as const,
  detail: (testId: string) => [...quizTestKeys.all, "detail", testId] as const,
};
